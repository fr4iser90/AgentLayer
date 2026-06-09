import { memo } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import { getAgentShowReasoning } from "../settings/agentReasoningPrefs";
import { AssistantProposalBody } from "./ProposalMessageBody";
import type { RunCard } from "./buildRunCards";
import { RunCardBlock } from "./RunCardBlock";
import { SecretRegisterCard } from "./SecretRegisterCard";
import { MessageFeedbackButtons } from "./MessageFeedbackButtons";
import {
  buildInterleavedTurnSegments,
  type TurnSegment,
} from "./interleavedTurnSegments";
import type { AgentTimelineEntry } from "./chatThreadStorage";
import type { Proposal, ProposalOption } from "../../lib/proposalParser";
import { TurnElapsedRuntime } from "./TurnElapsedRuntime";

const ReasoningPanel = memo(function ReasoningPanel({ text }: { text: string }) {
  const { t } = useTranslation(["chat"]);
  const trimmed = text.trim();
  if (!trimmed || !getAgentShowReasoning()) return null;
  return (
    <details className="mb-3 rounded-md border border-white/5 bg-black/25 px-3 py-2 text-xs text-neutral-500">
      <summary className="cursor-pointer select-none font-medium uppercase tracking-wide text-neutral-500">
        {t("chat:reasoningPanelLabel")}
      </summary>
      <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-neutral-500">{trimmed}</pre>
    </details>
  );
});

type Props = {
  content: string;
  reasoningContent?: string;
  timelineEntries: AgentTimelineEntry[];
  running?: boolean;
  createdAt?: number;
  auth: AuthContextValue;
  selectedByProposalId: Map<string, string | null>;
  onSelectProposalOption: (proposal: Proposal, option: ProposalOption) => void;
  onSecretSaved: (promptId: string, serviceKey: string) => void;
  expandedRunCardIds?: ReadonlySet<string>;
  onToggleRunCardExpanded?: (cardId: string) => void;
  conversationId?: string | null;
  messagePosition?: number;
  feedbackRating?: "up" | "down" | null;
  standInAuto?: boolean;
  /** Wall-clock start of this in-flight turn (ms); shows elapsed Laufzeit in the bubble only. */
  runStartedAtMs?: number | null;
  waitHint?: string | null;
};

const InterleavedStreamBody = memo(function InterleavedStreamBody({
  segments,
  auth,
  selectedByProposalId,
  onSelectProposalOption,
  onSecretSaved,
  expandedRunCardIds,
  onToggleRunCardExpanded,
}: {
  segments: TurnSegment[];
  auth: AuthContextValue;
  selectedByProposalId: Map<string, string | null>;
  onSelectProposalOption: (proposal: Proposal, option: ProposalOption) => void;
  onSecretSaved: (promptId: string, serviceKey: string) => void;
  expandedRunCardIds?: ReadonlySet<string>;
  onToggleRunCardExpanded?: (cardId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      {segments.map((seg) => {
        if (seg.type === "text") {
          const trimmed = seg.text.trim();
          if (!trimmed) return null;
          return (
            <AssistantProposalBody
              key={seg.key}
              content={seg.text}
              selectedByProposalId={selectedByProposalId}
              onSelectOption={onSelectProposalOption}
            />
          );
        }
        if (seg.type === "secret_prompt") {
          return (
            <SecretRegisterCard
              key={seg.key}
              prompt={seg.prompt}
              auth={auth}
              onSaved={onSecretSaved}
            />
          );
        }
        return (
          <RunCardBlock
            key={seg.key}
            card={seg.card}
            expanded={expandedRunCardIds?.has(seg.card.id)}
            onToggleExpanded={
              onToggleRunCardExpanded
                ? () => onToggleRunCardExpanded(seg.card.id)
                : undefined
            }
          />
        );
      })}
    </div>
  );
});

/** Assistant turn: text and tool cards interleaved in stream order (one bubble). */
export const AssistantTurnBlock = memo(function AssistantTurnBlock({
  content,
  reasoningContent,
  timelineEntries,
  running = false,
  createdAt,
  auth,
  selectedByProposalId,
  onSelectProposalOption,
  onSecretSaved,
  expandedRunCardIds,
  onToggleRunCardExpanded,
  conversationId,
  messagePosition,
  feedbackRating,
  standInAuto = false,
  runStartedAtMs = null,
  waitHint = null,
}: Props) {
  const { t } = useTranslation(["chat"]);
  const segments = buildInterleavedTurnSegments(content, timelineEntries);
  const hasStreamBody = segments.some(
    (s) =>
      (s.type === "text" && s.text.trim().length > 0) ||
      s.type === "card" ||
      s.type === "secret_prompt"
  );
  const timeLabel =
    createdAt != null
      ? new Date(createdAt).toLocaleTimeString(undefined, {
          hour: "2-digit",
          minute: "2-digit",
        })
      : null;

  return (
    <li className="flex w-full justify-end scroll-mt-4">
      <div className="max-w-[min(100%,42rem)] rounded-2xl border border-white/10 bg-[#1e1e1e] px-4 py-3 text-sm text-neutral-200 shadow-sm">
        <span className="mb-1 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
          {running && !hasStreamBody ? (
            <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-sky-400" />
          ) : null}
          {t("chat:roleAssistant")}
          {standInAuto ? (
            <span className="rounded bg-violet-900/40 px-1.5 py-0.5 text-[9px] font-normal normal-case text-violet-200">
              {t("chat:standInAutoBadge")}
            </span>
          ) : null}
          {timeLabel ? (
            <span className="font-normal normal-case text-surface-muted">{timeLabel}</span>
          ) : null}
        </span>
        {running && runStartedAtMs != null ? (
          <TurnElapsedRuntime startedAtMs={runStartedAtMs} className="mb-2" />
        ) : null}
        <ReasoningPanel text={reasoningContent ?? ""} />
        {hasStreamBody ? (
          <InterleavedStreamBody
            segments={segments}
            auth={auth}
            selectedByProposalId={selectedByProposalId}
            onSelectProposalOption={onSelectProposalOption}
            onSecretSaved={onSecretSaved}
            expandedRunCardIds={expandedRunCardIds}
            onToggleRunCardExpanded={onToggleRunCardExpanded}
          />
        ) : running ? (
          <p className="text-neutral-300/90">{waitHint?.trim() || t("chat:agentRunning")}</p>
        ) : null}
        {!running && messagePosition != null ? (
          <MessageFeedbackButtons
            auth={auth}
            conversationId={conversationId}
            messagePosition={messagePosition}
            initialRating={feedbackRating ?? null}
          />
        ) : null}
      </div>
    </li>
  );
});
