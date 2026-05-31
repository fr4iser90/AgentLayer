import type { ReactNode } from "react";
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
  className?: string;
  /** e.g. a &quot;+&quot; control to edit workspace-scoped MCP (parent owns modal). */
  mcpAddon?: ReactNode;
};

export function SessionRuntimeBar({ runtime, usage, contextMeta, className = "", mcpAddon }: Props) {
  const { t } = useTranslation(["workspace", "dashboard", "chat"]);
  const mcp = runtime?.mcp;
  const budget = runtime?.context;
  const hasUsage = usage.total > 0 || usage.rounds > 0;
  const providerPrompt = contextMeta?.provider_prompt_tokens;
  const hasProviderPrompt = providerPrompt != null && providerPrompt > 0;
  const windowTokens = contextMeta?.context_window_tokens ?? contextMeta?.budget_tokens ?? 0;
  const softLimit =
    contextMeta?.soft_limit_tokens ??
    (windowTokens > 0 && budget?.soft_limit_ratio
      ? Math.floor(windowTokens * budget.soft_limit_ratio)
      : 0);
  const hardLimit =
    contextMeta?.hard_limit_tokens ??
    (windowTokens > 0 && budget?.hard_limit_ratio
      ? Math.floor(windowTokens * budget.hard_limit_ratio)
      : 0);
  const showContext =
    Boolean(budget?.prep_enabled) &&
    (windowTokens > 0 ||
      softLimit > 0 ||
      hasProviderPrompt ||
      Boolean(contextMeta?.summary_active) ||
      Boolean(contextMeta?.at_soft_limit));
  if (!mcp && !hasUsage && !showContext) return null;

  const servers = mcp?.servers ?? [];
  const connected = servers.filter((s) => s.connected).length;
  const scope = mcp?.scope;

  const contextWarn =
    contextMeta?.at_hard_limit
      ? "hard"
      : contextMeta?.at_soft_limit
        ? "soft"
        : hasProviderPrompt && softLimit > 0 && providerPrompt >= softLimit
          ? "soft"
          : null;

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
              title={t("chat:contextBudgetTitle")}
            >
              {hasProviderPrompt
                ? t("chat:contextBudgetUsage", {
                    prompt: providerPrompt.toLocaleString(),
                    soft: softLimit.toLocaleString(),
                  })
                : t("chat:contextBudgetPending", {
                    soft: softLimit.toLocaleString(),
                  })}
              {contextMeta?.summary_active ? (
                <span className="ml-1 text-violet-300/85">{t("chat:contextCompacted")}</span>
              ) : null}
              {contextMeta?.loop_compaction_applied ? (
                <span className="ml-1 text-amber-300/85">{t("chat:contextLoopCompacted")}</span>
              ) : null}
              {contextMeta?.messages_dropped ? (
                <span className="ml-1 text-neutral-500">
                  {t("chat:contextDropped", { count: contextMeta.messages_dropped })}
                </span>
              ) : null}
            </span>
          </>
        ) : null}
        {hasUsage ? (
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
