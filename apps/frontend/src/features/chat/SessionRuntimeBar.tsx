import { Fragment, type ReactNode } from "react";
import type {
  ChatContextMeta,
  SessionRuntimePayload,
  TokenUsageTotals,
} from "../../lib/api";
import { useTranslation } from "react-i18next";

type Props = {
  runtime: SessionRuntimePayload | null;
  usage: TokenUsageTotals;
  contextMeta?: ChatContextMeta | null;
  agentRunning?: boolean;
  /** Agent-Modus: Kontext + Tokens immer anzeigen (auch 0 / —). */
  agentMode?: boolean;
  className?: string;
  mcpAddon?: ReactNode;
};

function mergeContextMeta(
  contextMeta: ChatContextMeta | null | undefined,
  runtime: SessionRuntimePayload | null
): ChatContextMeta | null {
  const cb = runtime?.context_budget;
  if (!contextMeta && !cb) return null;
  const base = { ...(contextMeta ?? {}) };
  if (cb) {
    if (base.context_window_tokens == null && cb.context_window_tokens != null) {
      base.context_window_tokens = cb.context_window_tokens;
    }
    if (base.soft_limit_tokens == null && cb.soft_limit_tokens != null) {
      base.soft_limit_tokens = cb.soft_limit_tokens;
    }
    if (base.hard_limit_tokens == null && cb.hard_limit_tokens != null) {
      base.hard_limit_tokens = cb.hard_limit_tokens;
    }
    if (!base.budget_source && cb.budget_source) {
      base.budget_source = cb.budget_source;
    }
    if (base.budget_tokens == null && cb.context_window_tokens != null) {
      base.budget_tokens = cb.context_window_tokens;
    }
  }
  return base;
}

function resolveSoftLimit(
  meta: ChatContextMeta | null,
  budget: SessionRuntimePayload["context"] | undefined
): number {
  if (meta?.soft_limit_tokens != null && meta.soft_limit_tokens > 0) {
    return meta.soft_limit_tokens;
  }
  const window =
    meta?.context_window_tokens ?? meta?.budget_tokens ?? budget?.fallback_budget_tokens ?? 0;
  if (window > 0 && budget?.soft_limit_ratio) {
    return Math.floor(window * budget.soft_limit_ratio);
  }
  return 0;
}

function resolveWindowTokens(
  meta: ChatContextMeta | null,
  budget: SessionRuntimePayload["context"] | undefined
): number {
  return (
    meta?.context_window_tokens ?? meta?.budget_tokens ?? budget?.fallback_budget_tokens ?? 0
  );
}

export function SessionRuntimeBar({
  runtime,
  usage,
  contextMeta,
  agentRunning = false,
  agentMode = false,
  className = "",
  mcpAddon,
}: Props) {
  const { t } = useTranslation(["workspace", "dashboard", "chat"]);
  const mcp = runtime?.mcp;
  const budget = runtime?.context;
  const mergedMeta = mergeContextMeta(contextMeta, runtime);
  const prepEnabled = budget?.prep_enabled !== false;

  const metaPrompt = mergedMeta?.provider_prompt_tokens;
  const usagePrompt = usage.prompt > 0 ? usage.prompt : null;
  const providerPrompt =
    metaPrompt != null && metaPrompt > 0
      ? metaPrompt
      : usagePrompt != null
        ? usagePrompt
        : null;
  const hasProviderPrompt = providerPrompt != null && providerPrompt > 0;
  const windowTokens = resolveWindowTokens(mergedMeta, budget);
  const softLimit = resolveSoftLimit(mergedMeta, budget);

  const showContext =
    agentMode ||
    (prepEnabled &&
      (agentRunning ||
        windowTokens > 0 ||
        softLimit > 0 ||
        hasProviderPrompt ||
        Boolean(mergedMeta?.summary_active) ||
        Boolean(mergedMeta?.at_soft_limit)));

  const showTokens = agentMode || usage.total > 0 || usage.rounds > 0;

  const showBar = Boolean(mcp) || showContext || showTokens;

  if (!showBar) return null;

  const servers = mcp?.servers ?? [];
  const connected = servers.filter((s) => s.connected).length;
  const scope = mcp?.scope;

  const contextWarn =
    mergedMeta?.at_hard_limit
      ? "hard"
      : mergedMeta?.at_soft_limit
        ? "soft"
        : hasProviderPrompt && softLimit > 0 && providerPrompt! >= softLimit
          ? "soft"
          : null;

  const budgetSource = (mergedMeta?.budget_source || "").trim();
  const messagesInPrompt =
    mergedMeta?.messages_in_prompt != null && mergedMeta.messages_in_prompt > 0
      ? mergedMeta.messages_in_prompt
      : null;

  const contextTitle = [
    t("chat:contextBudgetTitle"),
    budgetSource ? `source: ${budgetSource}` : "",
    windowTokens > 0 ? `window: ${windowTokens.toLocaleString()}` : "",
    softLimit > 0 ? `soft: ${softLimit.toLocaleString()}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  const contextLine = (() => {
    if (windowTokens <= 0) return <>{t("chat:contextBudgetWaiting")}</>;
    const windowStr = windowTokens.toLocaleString();
    const extras: ReactNode[] = [];
    if (softLimit > 0 && softLimit !== windowTokens) {
      extras.push(
        <span key="soft" className="text-neutral-500">
          {t("chat:contextSoftHint", { soft: softLimit.toLocaleString() })}
        </span>
      );
    }
    if (messagesInPrompt != null && !hasProviderPrompt) {
      extras.push(
        <span key="msgs" className="text-neutral-500">
          {t("chat:contextMessagesHint", { count: messagesInPrompt })}
        </span>
      );
    }
    if (budgetSource) {
      extras.push(
        <span key="src" className="text-neutral-500">
          {t("chat:contextBudgetSourceHint", { source: budgetSource })}
        </span>
      );
    }
    const main =
      hasProviderPrompt && windowTokens > 0
        ? t("chat:contextBudgetUsage", {
            prompt: providerPrompt!.toLocaleString(),
            window: windowStr,
          })
        : t("chat:contextBudgetPending", { window: windowStr });
    return (
      <Fragment>
        {main}
        {extras}
      </Fragment>
    );
  })();

  return (
    <div
      className={`rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-[10px] leading-snug text-neutral-300 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="font-semibold uppercase tracking-wide text-surface-muted">{t("workspace:mcp")}</span>
        {scope === "workspace" ? (
          <span
            className="rounded border border-sky-500/35 bg-sky-950/40 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-sky-200/90"
            title={t("workspace:mcpWorkspaceScopeTitle")}
          >
            {t("workspace:scopeWorkspace")}
          </span>
        ) : null}
        {mcpAddon ? <span className="flex items-center">{mcpAddon}</span> : null}
        {!mcp ? (
          <span className="text-neutral-500">—</span>
        ) : !mcp.enabled ? (
          <span className="text-neutral-500">{t("workspace:disabled")}</span>
        ) : !mcp.import_ok ? (
          <span className="text-amber-300/90" title={t("workspace:mcpPackageMissingTitle")}>
            {t("workspace:packageMissing")}
          </span>
        ) : mcp.config_error ? (
          <span className="text-red-400/90" title={mcp.config_error}>
            {t("workspace:configError")}
          </span>
        ) : servers.length === 0 ? (
          <span className="text-neutral-500">{t("workspace:noServers")}</span>
        ) : (
          <span
            className="tabular-nums"
            title={servers.map((s) => `${s.id}: ${s.connected ? `${s.tool_count} tools` : s.error || "down"}`).join("\n")}
          >
            <span className={connected > 0 ? "text-emerald-400/95" : "text-amber-300/90"}>{connected}</span>
            <span className="text-neutral-500">/{servers.length}</span>
            <span className="ml-1 text-neutral-500">{t("workspace:servers")}</span>
          </span>
        )}
        {showContext ? (
          <>
            <span className="text-neutral-600">·</span>
            <span className="font-semibold uppercase tracking-wide text-surface-muted">
              {t("chat:contextBudgetLabel")}
            </span>
            <span
              className={`tabular-nums ${
                contextWarn === "hard"
                  ? "text-red-300/95"
                  : contextWarn === "soft"
                    ? "text-amber-300/90"
                    : "text-neutral-200"
              }`}
              title={contextTitle}
            >
              {contextLine}
              {mergedMeta?.summary_active ? (
                <span className="ml-1 text-violet-300/85">{t("chat:contextCompacted")}</span>
              ) : null}
              {mergedMeta?.loop_compaction_applied ? (
                <span className="ml-1 text-amber-300/85">{t("chat:contextLoopCompacted")}</span>
              ) : null}
              {mergedMeta?.messages_dropped ? (
                <span className="ml-1 text-neutral-500">
                  {t("chat:contextDropped", { count: mergedMeta.messages_dropped })}
                </span>
              ) : null}
            </span>
          </>
        ) : null}
        {showTokens ? (
          <>
            <span className="text-neutral-600">·</span>
            <span className="font-semibold uppercase tracking-wide text-surface-muted">{t("dashboard:tokens")}</span>
            <span className="tabular-nums text-neutral-200">
              {t("dashboard:tokenUsage", {
                in: usage.prompt.toLocaleString(),
                out: usage.completion.toLocaleString(),
                total: usage.total.toLocaleString(),
              })}
              {usage.rounds > 0 ? (
                <span className="text-neutral-500"> {t("dashboard:llmRounds", { count: usage.rounds })}</span>
              ) : null}
            </span>
          </>
        ) : null}
      </div>
    </div>
  );
}
