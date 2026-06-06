import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import {
  applyModelCatalogSelection,
  defaultModelCatalogSelectValue,
  fetchModelCatalog,
  formatModelCatalogHint,
  composerSelectValueForThread,
  modelCatalogSelectValue,
  modelOptionLabel,
  resolveSendModelRouting,
  type ModelRow,
} from "../../lib/modelCatalog";
import type { ChatThread, UiMessage } from "../chat/chatThreadStorage";
import {
  createConversation,
  fetchConversationDetail,
  fetchConversationList,
  mapListItemToThread,
  putConversation,
} from "../chat/conversationsApi";
import { getDisabledToolNames } from "../settings/toolPrefs";
import type { PendingAttachment } from "../chat/messageFormat";
import {
  buildUserMessageContent,
  filesToAttachments,
  parseContentParts,
  toApiContent,
} from "../chat/messageFormat";
import { runDashboardAgentTurn } from "./dashboardAgentWs";
import { sanitizeDashboardAssistantText } from "./dashboardChatDisplay";
import { DashboardLayoutProposalInline } from "./DashboardLayoutProposalInline";
import { DashboardLayoutProposalPanel } from "./DashboardLayoutProposalPanel";
import { fetchActiveLayoutProposalSet } from "./layoutProposalShared";

type Msg = { role: "user" | "assistant"; content: string };

function dashboardThreadsForPanel(
  list: Record<string, unknown>[],
  readOnly: boolean
): ChatThread[] {
  const mapped = list.map(mapListItemToThread);
  const filtered = readOnly ? mapped.filter((t) => t.shared === true) : mapped;
  return [...filtered].sort((a, b) => b.updatedAt - a.updatedAt);
}

function pickDefaultDashboardThread(threads: ChatThread[], readOnly: boolean): ChatThread | null {
  if (threads.length === 0) return null;
  if (readOnly) {
    return threads.find((t) => t.shared === true) ?? threads[0]!;
  }
  return threads.find((t) => t.shared !== true) ?? threads[0]!;
}

function formatThreadOptionLabel(
  row: ChatThread,
  labels: { shared: string; personal: string; untitled: string }
): string {
  const prefix =
    row.shared === true
      ? `${labels.shared}: `
      : row.dashboardId
        ? `${labels.personal}: `
        : "";
  const title = row.title.trim() || labels.untitled;
  const n = row.messageCount ?? row.messages.length;
  return n > 0 ? `${prefix}${title} (${n})` : `${prefix}${title}`;
}

function formatUserBubbleForList(raw: string): string {
  const { parts } = parseContentParts(raw);
  if (!parts) return raw;
  const texts = parts
    .filter((p) => p.type === "text")
    .map((p) => String((p as { text?: string }).text ?? ""))
    .join(" ")
    .trim();
  const nImg = parts.filter((p) => p.type === "image_url").length;
  const head = texts || "(Bild-Anhang)";
  if (nImg) return `${head} · ${nImg} Bild${nImg > 1 ? "er" : ""}`;
  return head;
}

type Props = {
  dashboardId: string;
  dashboardTitle?: string;
  /** Dashboard viewers: show history but do not send or edit. */
  readOnly?: boolean;
  /** When set, pre-fill the composer (e.g. onboarding starter). */
  composeDraft?: string;
  /** Increment to push ``composeDraft`` into the textarea again. */
  composeDraftSeed?: number;
  /** Live dashboard data for layout preview cards. */
  dashboardData?: Record<string, unknown>;
  /** From notification / URL ``?proposals=`` — shows inline cards, no auto-modal. */
  initialProposalSetId?: string | null;
  /** After user applies a layout proposal. */
  onLayoutApplied?: () => void;
};

/**
 * Dashboard assistant: **personal** thread by default (only you). A **shared** team thread is optional:
 * create via API (`POST /v1/user/conversations` with `dashboard_id` + `shared: true`) if all members should see it.
 * Agent WebSocket (tools enabled) + `agent_dashboard_context`, same as full Chat agent mode.
 */
export function DashboardEmbeddedChat({
  dashboardId,
  dashboardTitle,
  readOnly = false,
  composeDraft,
  composeDraftSeed = 0,
  dashboardData = {},
  initialProposalSetId = null,
  onLayoutApplied,
}: Props) {
  const { t } = useTranslation(["dashboard", "errors", "chat"]);
  const auth = useAuth();
  const { accessToken } = auth;
  const [open, setOpen] = useState(true);
  const [modelRows, setModelRows] = useState<ModelRow[]>([]);
  const [modelsCatalogReady, setModelsCatalogReady] = useState(false);
  const [modelsCatalogHint, setModelsCatalogHint] = useState<string | null>(null);
  const [thread, setThread] = useState<ChatThread | null>(null);
  const [initErr, setInitErr] = useState<string | null>(null);
  const [initLoading, setInitLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [sendLoading, setSendLoading] = useState(false);
  const [sendErr, setSendErr] = useState<string | null>(null);
  const [sendSlowHint, setSendSlowHint] = useState<string | null>(null);
  const [newChatBusy, setNewChatBusy] = useState(false);
  const [threadSwitchBusy, setThreadSwitchBusy] = useState(false);
  const [threadOptions, setThreadOptions] = useState<ChatThread[]>([]);
  const [noSharedChatYet, setNoSharedChatYet] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [modelBeforeFirstSend, setModelBeforeFirstSend] = useState("");
  const lastModelSelectionRef = useRef("");
  const endRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeProposalSetId, setActiveProposalSetId] = useState<string | null>(null);
  const [enlargeProposalId, setEnlargeProposalId] = useState<string | null>(null);

  useEffect(() => {
    if (initialProposalSetId?.trim()) {
      setActiveProposalSetId(initialProposalSetId.trim());
      return;
    }
    if (readOnly) return;
    let cancelled = false;
    void (async () => {
      const ps = await fetchActiveLayoutProposalSet(auth, dashboardId);
      if (cancelled || !ps?.set_id) return;
      setActiveProposalSetId(ps.set_id);
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, dashboardId, initialProposalSetId, readOnly]);

  const handleLayoutApplied = useCallback(() => {
    setActiveProposalSetId(null);
    setEnlargeProposalId(null);
    onLayoutApplied?.();
  }, [onLayoutApplied]);

  useEffect(() => {
    if (!composeDraftSeed || !composeDraft?.trim()) return;
    setDraft(composeDraft);
    setOpen(true);
  }, [composeDraft, composeDraftSeed]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const { rows, agentlayer } = await fetchModelCatalog();
        if (cancelled) return;
        setModelRows(rows);
        setModelsCatalogHint(
          formatModelCatalogHint(agentlayer, { excludeUnreachableProviderHints: true })
        );
      } catch {
        if (!cancelled) {
          setModelRows([]);
          setModelsCatalogHint(t("errors:loadModelCatalogFailed"));
        }
      } finally {
        if (!cancelled) setModelsCatalogReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const reloadThreadOptions = useCallback(async () => {
    if (!accessToken || !dashboardId) return [] as ChatThread[];
    const list = await fetchConversationList(auth, { dashboardId });
    const options = dashboardThreadsForPanel(list, readOnly);
    setThreadOptions(options);
    return options;
  }, [accessToken, auth, dashboardId, readOnly]);

  useEffect(() => {
    if (!accessToken || !dashboardId) {
      setInitLoading(false);
      return;
    }
    let cancelled = false;
    setInitLoading(true);
    setInitErr(null);
    setThread(null);
    setThreadOptions([]);
    setNoSharedChatYet(false);
    void (async () => {
      try {
        const options = await reloadThreadOptions();
        if (cancelled) return;
        const pick = pickDefaultDashboardThread(options, readOnly);
        if (pick?.id) {
          const full = await fetchConversationDetail(auth, pick.id);
          if (cancelled) return;
          setThread(full);
          return;
        }
        if (readOnly) {
          if (!cancelled) setNoSharedChatYet(true);
          return;
        }
        /* No auto-create: first message creates a private dashboard thread (avoids empty rows in /chat). */
        if (!cancelled) setThread(null);
      } catch (e) {
        if (!cancelled) {
          setInitErr(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setInitLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, auth, readOnly, dashboardId, reloadThreadOptions]);

  const switchDashboardThread = useCallback(
    async (conversationId: string) => {
      if (sendLoading || newChatBusy || threadSwitchBusy) return;
      if (!conversationId) {
        if (readOnly) return;
        setThread(null);
        setDraft("");
        setPendingAttachments([]);
        setSendErr(null);
        setSendSlowHint(null);
        setActiveProposalSetId(null);
        setEnlargeProposalId(null);
        return;
      }
      if (thread?.id === conversationId) return;
      setThreadSwitchBusy(true);
      setSendErr(null);
      setSendSlowHint(null);
      try {
        const full = await fetchConversationDetail(auth, conversationId);
        setThread(full);
        setDraft("");
        setPendingAttachments([]);
        setActiveProposalSetId(null);
        setEnlargeProposalId(null);
      } catch (e) {
        setSendErr(e instanceof Error ? e.message : String(e));
      } finally {
        setThreadSwitchBusy(false);
      }
    },
    [auth, newChatBusy, readOnly, sendLoading, thread?.id, threadSwitchBusy]
  );

  const messages: Msg[] = useMemo(() => {
    if (!thread) return [];
    return thread.messages.map((m) => ({
      role: m.role === "assistant" ? "assistant" : "user",
      content:
        m.role === "user"
          ? formatUserBubbleForList(String(m.content ?? ""))
          : String(m.content ?? ""),
    }));
  }, [thread]);

  const addPickedFiles = useCallback(async (files: FileList | null) => {
    if (!files?.length || readOnly) return;
    const next = await filesToAttachments(files);
    setPendingAttachments((prev) => [...prev, ...next]);
  }, [readOnly]);

  useEffect(() => {
    if (open && endRef.current) {
      endRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, open, sendLoading, activeProposalSetId]);

  const defaultSelectValue = useMemo(
    () => defaultModelCatalogSelectValue(modelRows),
    [modelRows]
  );
  const modelSelectValue = useMemo(() => {
    if (thread?.model?.trim()) {
      return composerSelectValueForThread(
        modelRows,
        thread.model,
        thread.modelProvider,
        defaultSelectValue
      );
    }
    if (modelBeforeFirstSend.trim()) {
      return composerSelectValueForThread(
        modelRows,
        modelBeforeFirstSend,
        undefined,
        defaultSelectValue
      );
    }
    return defaultSelectValue;
  }, [thread?.model, thread?.modelProvider, modelBeforeFirstSend, modelRows, defaultSelectValue]);

  useEffect(() => {
    if (modelSelectValue.includes(":")) {
      lastModelSelectionRef.current = modelSelectValue;
    }
  }, [modelSelectValue]);

  const setModelOnThread = useCallback(
    (raw: string) => {
      lastModelSelectionRef.current = raw;
      const { model, modelProvider } = applyModelCatalogSelection(raw, modelRows);
      setThread((t) => (t ? { ...t, model, modelProvider, updatedAt: Date.now() } : t));
    },
    [modelRows]
  );

  const startNewDashboardChat = useCallback(async () => {
    if (readOnly || sendLoading || newChatBusy || !accessToken) return;
    const routed = resolveSendModelRouting(modelRows, {
      lastSelection: lastModelSelectionRef.current,
      modelSelectValue,
      defaultSelectValue,
      threadModel: (thread?.model || modelBeforeFirstSend || modelRows[0]?.id || "").trim(),
      threadProvider: thread?.modelProvider,
    });
    if (!routed) {
      setSendErr(t("dashboard:resolveModelProviderFailed"));
      return;
    }
    const mdl = routed.model;
    const provider = routed.provider;
    const title = dashboardTitle?.trim()
      ? t("dashboard:assistantTitleWithDashboard", { title: dashboardTitle.trim() })
      : t("dashboard:assistantTitleFallback");
    setNewChatBusy(true);
    setSendErr(null);
    setSendSlowHint(null);
    try {
      const created = await createConversation(auth, {
        title,
        mode: "chat",
        model: mdl,
        messages: [],
        agent_log: [],
        dashboard_id: dashboardId,
        shared: false,
        model_catalog_owned_by: provider,
      });
      lastModelSelectionRef.current = routed.selectValue;
      setThread({ ...created, model: mdl, modelProvider: provider });
      setDraft("");
      setPendingAttachments([]);
      setActiveProposalSetId(null);
      setEnlargeProposalId(null);
      setModelBeforeFirstSend(routed.selectValue);
      await reloadThreadOptions();
    } catch (e) {
      setSendErr(e instanceof Error ? e.message : String(e));
    } finally {
      setNewChatBusy(false);
    }
  }, [
    accessToken,
    auth,
    dashboardId,
    dashboardTitle,
    defaultSelectValue,
    modelBeforeFirstSend,
    modelRows,
    modelSelectValue,
    newChatBusy,
    readOnly,
    sendLoading,
    t,
    reloadThreadOptions,
    thread?.model,
    thread?.modelProvider,
  ]);

  const send = useCallback(async () => {
    if (readOnly) return;
    const userContent = buildUserMessageContent(draft, pendingAttachments);
    if (!userContent || !accessToken || sendLoading) return;
    const routed = resolveSendModelRouting(modelRows, {
      lastSelection: lastModelSelectionRef.current,
      modelSelectValue,
      defaultSelectValue,
      threadModel: (thread?.model || modelBeforeFirstSend || modelRows[0]?.id || "").trim(),
      threadProvider: thread?.modelProvider,
    });
    if (!routed) {
      setSendErr(t("dashboard:resolveModelProviderFailed"));
      return;
    }
    lastModelSelectionRef.current = routed.selectValue;
    const mdl = routed.model;
    const provider = routed.provider;
    setSendErr(null);
    let prev = thread;
    if (!prev) {
      const title = dashboardTitle?.trim()
        ? t("dashboard:assistantTitleWithDashboard", { title: dashboardTitle.trim() })
        : t("dashboard:assistantTitleFallback");
      try {
        const created = await createConversation(auth, {
          title,
          mode: "chat",
          model: mdl,
          messages: [],
          agent_log: [],
          dashboard_id: dashboardId,
          shared: false,
          model_catalog_owned_by: provider,
        });
        prev = { ...created, model: mdl, modelProvider: provider };
        setThread(prev);
        void reloadThreadOptions();
      } catch (e) {
        setSendErr(e instanceof Error ? e.message : String(e));
        return;
      }
    }
    const userCreatedAt = Date.now();
    const nextMessages: UiMessage[] = [
      ...prev.messages,
      { role: "user", content: userContent, createdAt: userCreatedAt },
    ];
    const nextThread: ChatThread = {
      ...prev,
      model: mdl,
      modelProvider: provider,
      messages: nextMessages,
      updatedAt: Date.now(),
    };
    setThread(nextThread);
    const draftSnap = draft;
    const attachSnap = pendingAttachments;
    setDraft("");
    setPendingAttachments([]);
    setSendErr(null);
    setSendSlowHint(null);
    setSendLoading(true);
    try {
      await putConversation(auth, nextThread);
    } catch (e) {
      setSendErr(e instanceof Error ? e.message : String(e));
      setThread(prev);
      setDraft(draftSnap);
      setPendingAttachments(attachSnap);
      setSendLoading(false);
      return;
    }
    try {
      const disabledTools = getDisabledToolNames();
      const assistantCreatedAt = Date.now();
      const content = await runDashboardAgentTurn({
        accessToken: accessToken!,
        model: mdl,
        provider,
        messages: nextMessages.map((x) => ({
          role: x.role,
          content: toApiContent(x.content),
        })),
        dashboardId,
        conversationId: nextThread.id,
        disabledTools,
        onSlow: () => {
          setSendSlowHint(t("dashboard:embeddedChatSlowHint"));
        },
        onDelta: (acc) => {
          const clean = sanitizeDashboardAssistantText(acc);
          setThread({
            ...nextThread,
            messages: [...nextMessages, { role: "assistant", content: clean, createdAt: assistantCreatedAt }],
            updatedAt: Date.now(),
          });
        },
        onToolDone: (ev) => {
          const isPropose =
            ev.name === "propose_layouts" ||
            ev.name === "dashboard.propose_layouts" ||
            ev.name.endsWith(".propose_layouts");
          if (isPropose && ev.proposalSetId && ev.ok !== false) {
            setActiveProposalSetId(ev.proposalSetId);
          }
        },
      });
      const finalContent = sanitizeDashboardAssistantText(content.trim() || "(empty)");
      const withAssistant: ChatThread = {
        ...nextThread,
        messages: [
          ...nextMessages,
          { role: "assistant", content: finalContent || "(empty)", createdAt: assistantCreatedAt },
        ],
        updatedAt: Date.now(),
      };
      setThread(withAssistant);
      await putConversation(auth, withAssistant);
      void reloadThreadOptions();
    } catch (e) {
      setSendErr(e instanceof Error ? e.message : String(e));
      setThread(nextThread);
      setDraft(draftSnap);
      setPendingAttachments(attachSnap);
    } finally {
      setSendLoading(false);
    }
  }, [
    accessToken,
    auth,
    draft,
    modelSelectValue,
    defaultSelectValue,
    modelBeforeFirstSend,
    pendingAttachments,
    modelRows,
    readOnly,
    sendLoading,
    thread,
    dashboardId,
    dashboardTitle,
    reloadThreadOptions,
    t,
  ]);

  const showThreadPicker =
    !initLoading && (readOnly ? threadOptions.length > 0 : !noSharedChatYet);

  const hasComposerPayload =
    draft.trim().length > 0 ||
    pendingAttachments.some((a) => a.kind === "image" || a.kind === "textfile");

  const canSend =
    !readOnly &&
    hasComposerPayload &&
    !sendLoading &&
    !!accessToken &&
    !initLoading &&
    modelRows.length > 0 &&
    !!(modelSelectValue || defaultSelectValue).trim();

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-surface-border bg-surface-raised/40">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full shrink-0 items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-medium text-white hover:bg-white/5 lg:py-2"
      >
        <span>
          {t("dashboard:assistant")}
          <span className="ml-1 font-normal text-surface-muted">
            {dashboardTitle ? `· ${dashboardTitle}` : ""}
          </span>
        </span>
        <span className="text-surface-muted">{open ? "▼" : "▶"}</span>
      </button>
      {open ? (
        <div className="flex min-h-0 flex-1 flex-col border-t border-surface-border">
          <div className="flex shrink-0 items-start justify-between gap-2 px-3 pt-2">
            <p className="min-w-0 flex-1 text-[11px] leading-snug text-surface-muted">
              {readOnly
                ? t("dashboard:embeddedChatTeamHint")
                : t("dashboard:embeddedChatPrivateHint")}
            </p>
            {!readOnly ? (
              <button
                type="button"
                disabled={sendLoading || newChatBusy || initLoading}
                title={t("dashboard:embeddedChatNewThreadHint")}
                className="shrink-0 rounded-md border border-white/15 bg-black/30 px-2 py-1 text-[10px] font-medium text-neutral-200 hover:bg-white/10 disabled:opacity-40"
                onClick={() => void startNewDashboardChat()}
              >
                {newChatBusy ? t("dashboard:loading") : t("dashboard:embeddedChatNewThread")}
              </button>
            ) : null}
          </div>
          {initLoading ? (
            <div className="px-3 py-4 text-sm text-surface-muted">{t("dashboard:embeddedChatLoading")}</div>
          ) : noSharedChatYet && !thread ? (
            <div className="px-3 py-4 text-xs leading-snug text-surface-muted">
              {t("dashboard:embeddedChatNoVisibleYet")}
            </div>
          ) : initErr ? (
            <div className="mx-3 mb-2 rounded border border-red-500/40 bg-red-950/30 px-2 py-2 text-xs text-red-200">
              {initErr}
            </div>
          ) : (
            <>
              {showThreadPicker ? (
                <div className="shrink-0 px-3 pt-2">
                  <label className="mb-0.5 block text-[10px] text-surface-muted">
                    {t("dashboard:embeddedChatThreadLabel")}
                  </label>
                  <select
                    className="w-full rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-white"
                    value={thread?.id ?? ""}
                    disabled={
                      readOnly
                        ? threadOptions.length <= 1 || threadSwitchBusy || sendLoading
                        : threadSwitchBusy || sendLoading || newChatBusy
                    }
                    onChange={(e) => void switchDashboardThread(e.target.value)}
                  >
                    {!readOnly ? (
                      <option value="">{t("dashboard:embeddedChatDraftThread")}</option>
                    ) : null}
                    {threadOptions.map((row) => (
                      <option key={row.id} value={row.id}>
                        {formatThreadOptionLabel(row, {
                          shared: t("chat:visibilitySharedLabel"),
                          personal: t("chat:visibilityPersonalLabel"),
                          untitled: t("dashboard:embeddedChatUntitledThread"),
                        })}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
              <div className="shrink-0 px-3 pt-2">
                <label className="mb-0.5 block text-[10px] text-surface-muted">{t("dashboard:modelLabel")}</label>
                <select
                  className="w-full rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-white"
                  value={modelSelectValue}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (thread) {
                      const { model, modelProvider } = applyModelCatalogSelection(v, modelRows);
                      setModelOnThread(v);
                      if (!readOnly) {
                        void putConversation(auth, {
                          ...thread,
                          model,
                          modelProvider,
                          updatedAt: Date.now(),
                        }).catch(() => {});
                      }
                    } else {
                      lastModelSelectionRef.current = v;
                      setModelBeforeFirstSend(v);
                    }
                  }}
                  disabled={readOnly || !modelsCatalogReady || modelRows.length === 0}
                >
                  {!modelsCatalogReady ? (
                    <option value="">{t("dashboard:loading")}</option>
                  ) : modelRows.length === 0 ? (
                    <option value="">{modelsCatalogHint ?? t("dashboard:noModels")}</option>
                  ) : (
                    modelRows.map((row) => (
                      <option key={modelCatalogSelectValue(row)} value={modelCatalogSelectValue(row)}>
                        {modelOptionLabel(row)}
                      </option>
                    ))
                  )}
                </select>
                {modelsCatalogReady && modelsCatalogHint ? (
                  <p className="mt-1 text-[10px] leading-snug text-amber-300/90">{modelsCatalogHint}</p>
                ) : null}
              </div>
              {sendErr ? (
                <div className="mx-3 mt-2 rounded border border-red-500/40 bg-red-950/30 px-2 py-1.5 text-xs text-red-200">
                  {sendErr}
                </div>
              ) : null}
              {sendSlowHint && sendLoading ? (
                <div className="mx-3 mt-2 rounded border border-amber-500/30 bg-amber-950/20 px-2 py-1.5 text-xs text-amber-200">
                  {sendSlowHint}
                </div>
              ) : null}
              <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
                <div className="max-h-[min(320px,40vh)] overflow-y-auto rounded-lg border border-white/10 bg-black/20 px-2 py-2 text-sm lg:max-h-[min(480px,calc(100vh-280px))]">
                  {messages.length === 0 ? (
                    <p className="text-xs text-surface-muted">
                      {thread
                        ? t("dashboard:embeddedChatEmptyWithThread")
                        : t("dashboard:embeddedChatEmptyNoThread")}
                    </p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {messages.map((m, i) => (
                        <li
                          key={`${thread?.id ?? "t"}-${i}-${m.role}`}
                          className={`rounded-md px-2 py-1.5 text-xs ${
                            m.role === "user"
                              ? "border border-sky-900/40 bg-sky-950/20 text-neutral-100"
                              : "border border-white/10 bg-[#1a1a1a] text-neutral-200"
                          }`}
                        >
                          <span className="mb-0.5 block text-[9px] font-medium uppercase text-surface-muted">
                            {m.role === "user" ? t("dashboard:you") : t("dashboard:assistant")}
                          </span>
                          <div className="whitespace-pre-wrap">{m.content}</div>
                        </li>
                      ))}
                      {sendLoading ? (
                        <li className="text-xs text-sky-300/80">…</li>
                      ) : null}
                      {activeProposalSetId && !readOnly ? (
                        <li className="rounded-md border border-emerald-500/20 bg-emerald-950/10 px-2 py-1.5">
                          <span className="mb-1 block text-[9px] font-medium uppercase text-surface-muted">
                            {t("dashboard:assistant")}
                          </span>
                          <DashboardLayoutProposalInline
                            dashboardId={dashboardId}
                            setId={activeProposalSetId}
                            data={dashboardData}
                            onEnlarge={(proposalId) => setEnlargeProposalId(proposalId)}
                            onApplied={handleLayoutApplied}
                          />
                        </li>
                      ) : null}
                      <div ref={endRef} />
                    </ul>
                  )}
                </div>
              </div>
              <div className="shrink-0 border-t border-surface-border p-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  accept="image/*,.txt,.md,.json,.csv,.log,.yaml,.yml"
                  onChange={(e) => {
                    const files = e.target.files;
                    e.target.value = "";
                    void addPickedFiles(files);
                  }}
                />
                {pendingAttachments.length > 0 ? (
                  <ul className="mb-2 flex flex-wrap gap-1.5">
                    {pendingAttachments.map((a, idx) => (
                      <li
                        key={`${a.name}-${idx}`}
                        className="flex max-w-full items-center gap-1 rounded border border-white/10 bg-black/30 px-2 py-0.5 text-[10px] text-neutral-300"
                      >
                        <span className="truncate" title={a.kind === "unsupported" ? a.hint : a.name}>
                          {a.name}
                          {a.kind === "unsupported" ? t("dashboard:attachmentSkip") : ""}
                        </span>
                        <button
                          type="button"
                          className="text-surface-muted hover:text-white"
                          aria-label={t("dashboard:remove")}
                          onClick={() => setPendingAttachments((p) => p.filter((_, i) => i !== idx))}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={readOnly || sendLoading}
                    className="shrink-0 rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-surface-muted hover:bg-white/5 hover:text-white disabled:opacity-40"
                    title={t("dashboard:attachTitle")}
                    aria-label={t("dashboard:attach")}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    +
                  </button>
                  <input
                    type="text"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void send();
                      }
                    }}
                    placeholder={t("dashboard:messagePlaceholder")}
                    className="min-w-0 flex-1 rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50"
                    disabled={readOnly || sendLoading}
                  />
                  <button
                    type="button"
                    disabled={!canSend}
                    onClick={() => void send()}
                    className="shrink-0 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                  >
                    {t("dashboard:send")}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      ) : null}
      {enlargeProposalId && activeProposalSetId ? (
        <DashboardLayoutProposalPanel
          dashboardId={dashboardId}
          setId={activeProposalSetId}
          data={dashboardData}
          initialProposalId={enlargeProposalId}
          onApplied={handleLayoutApplied}
          onClose={() => setEnlargeProposalId(null)}
        />
      ) : null}
    </div>
  );
}
