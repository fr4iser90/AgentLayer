import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { ConfirmModal } from "../components/ConfirmModal";
import { apiFetch, addUsageTotals, emptyTokenUsage, fetchSessionRuntime, type ChatContextMeta, type SessionRuntimePayload, type TokenUsageTotals, type WorkspaceApiRecord } from "../lib/api";
import {
  deleteWorkspaceApi,
  isAgentlayerSelfWorkspace,
} from "../lib/workspacesApi";
import {
  applyModelCatalogSelection,
  defaultModelCatalogSelectValue,
  fetchModelCatalog,
  formatEmptyChatModelCatalogHint,
  formatModelCatalogHint,
  catalogModelOptionUnreachableTitle,
  isCatalogModelOptionDisabled,
  modelCatalogSelectValue,
  modelOptionLabel,
  normalizeCatalogRoutingToken,
  parseModelCatalogSelection,
  composerSelectValueForThread,
  resolveSendModelRouting,
  type ModelCatalogAgentlayer,
  type ModelRow,
} from "../lib/modelCatalog";
import {
  NEW_CHAT_TITLE,
  type AgentTimelineEntry,
  type AgentTurnLog,
  type ChatMode,
  type ChatThread,
  type UiMessage,
  exportThreadJson,
  newMessageId,
  titleFromFirstMessage,
} from "../features/chat/chatThreadStorage";
import {
  activityForTurn,
  appendTimelineEntry,
  archiveTurnBeforeNewPrompt,
  latestUserMessageId,
  markSecretPromptSaved,
  serializeAgentLogPayload,
} from "../features/chat/agentLogStorage";
import { AgentActivityPanel } from "../features/chat/AgentActivityPanel";
import { AssistantTurnBlock } from "../features/chat/AssistantTurnBlock";
import { indexActivityToTimeline, type IndexActivityEvent } from "../features/chat/indexActivity";
import { buildInterleavedTurnSegments } from "../features/chat/interleavedTurnSegments";
import { timelineForTurn, userTurnIdBeforeAssistant } from "../features/chat/turnRunCards";
import {
  formatOptionSelection,
  type Proposal,
  type ProposalOption,
} from "../lib/proposalParser";
import { TurnNavigator, TurnNavigatorHorizontal, buildTurnItems } from "../features/chat/TurnNavigator";
import { useChatScroll } from "../features/chat/useChatScroll";

/** Dashboard-linked thread: show whether other members see messages (shared) or only you (personal). */
function DashboardChatVisibilityBadge({ thread }: { thread: Pick<ChatThread, "dashboardId" | "shared"> }) {
  const { t } = useTranslation(["chat"]);
  if (!thread.dashboardId) return null;
  const shared = thread.shared === true;
  if (shared) {
    return (
      <span
        className="inline-flex shrink-0 items-center rounded-full border border-amber-400/40 bg-amber-950/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-100/95"
        title={t("chat:visibilitySharedTitle")}
      >
        {t("chat:visibilitySharedLabel")}
      </span>
    );
  }
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-full border border-emerald-500/35 bg-emerald-950/45 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-100/90"
      title={t("chat:visibilityPersonalTitle")}
    >
      {t("chat:visibilityPersonalLabel")}
    </span>
  );
}
import {
  createConversation,
  deleteConversationApi,
  fetchConversationDetail,
  fetchConversationList,
  mapListItemToThread,
  mergeServerThreadWithLocal,
  putConversation,
} from "../features/chat/conversationsApi";
import {
  buildUserMessageContent,
  filesToAttachments,
  toApiContent,
  userMessagePlainText,
  userMessageToComposerState,
  type PendingAttachment,
} from "../features/chat/messageFormat";
import { UserMessageBubble } from "../features/chat/UserMessageBubble";
import { getDisabledToolNames } from "../features/settings/toolPrefs";
import { getAgentStreamLlm, setAgentStreamLlm } from "../features/settings/agentStreamPrefs";
import {
  buildSidebarGroups,
  filterThreadsForChatSidebar,
  threadsVisibleInSidebar,
} from "../features/chat/groupThreadsForSidebar";
import { SessionRuntimeBar } from "../features/chat/SessionRuntimeBar";
import {
  getChatComposerHeaderCollapsed,
  setChatComposerHeaderCollapsed,
} from "../features/chat/chatComposerHeaderPrefs";
import {
  getChatProjectPanelOpen,
  setChatProjectPanelOpen,
} from "../features/chat/chatProjectPanelPrefs";
import {
  getShowSubagentsInActivity,
  setShowSubagentsInActivity as persistShowSubagentsPref,
} from "../features/chat/chatSubagentPrefs";
import { handleSubagentWsEvent } from "../features/chat/subagentActivity";
import { formatToolStepLabel } from "../features/chat/toolStepLabel";
import { CodingWorkspacePanels } from "../features/workspace/CodingWorkspacePanels";
import { WorkspaceRetrievalBar } from "../features/workspace/WorkspaceRetrievalBar";
import { WorkspaceMcpModal } from "../features/workspace/WorkspaceMcpModal";
import { shouldIsolateWorkspaceThread } from "../features/workspace/chatWorkspaceNav";
import { confirmNewChatForWorkspace } from "../features/workspace/confirmWorkspaceScope";
import { streamOpenAiChatChunks } from "../features/chat/openaiSseStream";
import { formatMessageTime, inferMissingMessageTimestamps } from "../features/chat/messageTimestamps";


function wsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/v1/chat?token=${encodeURIComponent(token)}`;
}

/** `?dashboard=<uuid>` — validated; server re-checks access. */
function parseDashboardQueryParam(raw: string | null): string | null {
  if (!raw || !raw.trim()) return null;
  const s = raw.trim();
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s)
  ) {
    return null;
  }
  return s;
}

function threadMessageCount(t: ChatThread): number {
  return t.messageCount ?? t.messages.length;
}

function assistantFromCompletion(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const d = data as {
    choices?: Array<{ message?: { content?: unknown } }>;
  };
  const c = d.choices?.[0]?.message?.content;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    return c
      .map((part: unknown) => {
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text?: string }).text ?? "");
        }
        return "";
      })
      .join("");
  }
  return "";
}

function chatMessageHasVisibleContent(m: UiMessage): boolean {
  return (m.content ?? "").trim().length > 0;
}

function messagesWithStreamedAssistant(baseline: UiMessage[], accumulated: string): UiMessage[] {
  if (!accumulated.trim()) return baseline;
  const last = baseline[baseline.length - 1];
  const createdAt =
    last?.role === "assistant" && last.createdAt != null ? last.createdAt : Date.now();
  if (last?.role === "assistant") {
    return [...baseline.slice(0, -1), { role: "assistant", content: accumulated, createdAt }];
  }
  return [...baseline, { role: "assistant", content: accumulated, createdAt }];
}

type QueuedComposerMessage = {
  id: string;
  draft: string;
  attachments: PendingAttachment[];
};

type SendTurnOptions = {
  /** Re-run the API for an existing user message (no duplicate user row). */
  resendUserMsgId?: string;
};

type InFlightTurnSnapshot = {
  threadId: string;
  userMsgId: string;
  draft: string;
  attachments: PendingAttachment[];
  priorMessages: UiMessage[];
  priorTitle: string;
  priorAgentLog: AgentTimelineEntry[];
  priorTurnLogs: AgentTurnLog[];
  /** When true, cancel removes the user message and restores the composer draft. */
  rewindUserMessage: boolean;
};

function queueItemPreview(item: QueuedComposerMessage): string {
  const text = buildUserMessageContent(item.draft, item.attachments);
  if (text.length <= 120) return text;
  return `${text.slice(0, 117)}…`;
}

function assistantMessage(content: string, prior?: UiMessage | null): UiMessage {
  const createdAt =
    prior?.role === "assistant" && prior.createdAt != null ? prior.createdAt : Date.now();
  return { role: "assistant", content, createdAt };
}

function stripTrailingEmptyAssistantMessages(msgs: UiMessage[]): UiMessage[] {
  let out = [...msgs];
  while (out.length > 0) {
    const last = out[out.length - 1]!;
    if (last.role === "assistant" && !chatMessageHasVisibleContent(last)) {
      out = out.slice(0, -1);
    } else break;
  }
  return out;
}

function stripTrailingAssistantsAfterLastUser(msgs: UiMessage[]): UiMessage[] {
  let out = [...msgs];
  while (out.length > 0 && out[out.length - 1]?.role === "assistant") {
    out = out.slice(0, -1);
  }
  return out;
}

function lastUserMessageIndex(msgs: UiMessage[]): number {
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    if (msgs[i]?.role === "user") return i;
  }
  return -1;
}

function turnHasAssistantAfter(msgs: UiMessage[], userMsgId: string): boolean {
  const idx = msgs.findIndex((m) => m.id === userMsgId && m.role === "user");
  if (idx < 0) return false;
  return msgs.slice(idx + 1).some((m) => m.role === "assistant");
}

export function ChatPage() {
  const { t } = useTranslation(["chat", "errors", "admin", "dashboard", "workspace", "setup"]);
  const suggested = useMemo(
    () => [t("chat:suggested1"), t("chat:suggested2"), t("chat:suggested3")],
    [t]
  );
  const auth = useAuth();
  const { accessToken, user } = auth;
  const userId = user?.id ?? "";
  const [searchParams, setSearchParams] = useSearchParams();

  const dashboardChatId = useMemo(
    () => parseDashboardQueryParam(searchParams.get("dashboard")),
    [searchParams]
  );
  const [dashboardChatTitle, setDashboardChatTitle] = useState<string | null>(null);
  const agentDashboardPayload = useMemo(
    () =>
      dashboardChatId
        ? { agent_dashboard_context: { dashboard_id: dashboardChatId } }
        : ({} as Record<string, unknown>),
    [dashboardChatId]
  );

  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelRows, setModelRows] = useState<ModelRow[]>([]);
  const [modelsCatalogReady, setModelsCatalogReady] = useState(false);
  const [modelsCatalogHint, setModelsCatalogHint] = useState<string | null>(null);
  const [modelCatalogAgentlayer, setModelCatalogAgentlayer] = useState<ModelCatalogAgentlayer | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [composerDragActive, setComposerDragActive] = useState(false);
  const [dashboardTitles, setDashboardTitles] = useState<Record<string, string>>({});
  const [sessionRuntime, setSessionRuntime] = useState<SessionRuntimePayload | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsageTotals>(() => emptyTokenUsage());
  const [chatContextMeta, setChatContextMeta] = useState<ChatContextMeta | null>(null);

  const isAdminUser = (user?.role ?? "").toLowerCase() === "admin";
  /** Single Chat UI: everyone uses General; specialists via agent_delegate tool. */
  const composerAgentId = "general";

  const [workspaces, setWorkspaces] = useState<WorkspaceApiRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [showWorkspaceMcpModal, setShowWorkspaceMcpModal] = useState(false);
  const [workspaceScopeHint, setWorkspaceScopeHint] = useState<string | null>(null);
  const [composerHeaderCollapsed, setComposerHeaderCollapsed] = useState(false);
  const [projectPanelOpen, setProjectPanelOpen] = useState(false);
  const [projectTreeRefreshKey, setProjectTreeRefreshKey] = useState(0);
  const [showSubagentsInActivity, setShowSubagentsInActivity] = useState(true);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [selectedProposalOptions, setSelectedProposalOptions] = useState<
    Map<string, { proposal: Proposal; option: ProposalOption }>
  >(new Map());
  const [deleteProjectTarget, setDeleteProjectTarget] = useState<WorkspaceApiRecord | null>(
    null
  );
  const [deletingProject, setDeletingProject] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const agentHandlerRef = useRef<(ev: MessageEvent) => void>(() => {});
  /** User cancelled before the chat frame was sent (e.g. while WebSocket connects). */
  const cancelAgentTurnRef = useRef(false);
  /** Snapshot of the in-flight turn for cancel-restore and resend bookkeeping. */
  const inFlightTurnRef = useRef<InFlightTurnSnapshot | null>(null);
  /** Skip draining the composer queue after cancel-restore (user may edit before re-sending). */
  const skipQueueDrainOnFinishRef = useRef(false);
  /** In-flight HTTP chat completion (stream or JSON). */
  const chatAbortControllerRef = useRef<AbortController | null>(null);
  const activeThreadIdRef = useRef<string | null>(null);
  const lastModelSelectionRef = useRef("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const toolStartTimesRef = useRef<Map<string, number>>(new Map());
  const subagentStartTimesRef = useRef<Map<string, number>>(new Map());
  const agentTurnBaselineRef = useRef<UiMessage[] | null>(null);
  const streamDeltaAccRef = useRef("");
  const agentStreamEnabledThisTurnRef = useRef(false);
  const agentTurnFinishRef = useRef<(() => void) | null>(null);
  const composerQueueRef = useRef<Map<string, QueuedComposerMessage[]>>(new Map());
  const [composerQueueVersion, setComposerQueueVersion] = useState(0);
  const drainComposerQueueRef = useRef<() => void>(() => {});
  const runChatHttpRef = useRef<(queued?: QueuedComposerMessage, opts?: SendTurnOptions) => Promise<void>>(async () => {});
  const runAgentWsRef = useRef<(queued?: QueuedComposerMessage, opts?: SendTurnOptions) => Promise<void>>(async () => {});
  const threadsRef = useRef(threads);
  const persistAgentLogTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [agentStreamLlmUi, setAgentStreamLlmUi] = useState(() => getAgentStreamLlm());
  activeThreadIdRef.current = activeThreadId;
  threadsRef.current = threads;

  const flushPersistAgentLog = useCallback(() => {
    if (persistAgentLogTimerRef.current) {
      clearTimeout(persistAgentLogTimerRef.current);
      persistAgentLogTimerRef.current = null;
    }
    const tid = activeThreadIdRef.current;
    if (!tid) return;
    const th = threadsRef.current.find((t) => t.id === tid);
    if (!th) return;
    void putConversation(auth, th).catch(() => {});
  }, [auth]);

  const schedulePersistAgentLog = useCallback(() => {
    if (persistAgentLogTimerRef.current) clearTimeout(persistAgentLogTimerRef.current);
    persistAgentLogTimerRef.current = setTimeout(() => {
      persistAgentLogTimerRef.current = null;
      flushPersistAgentLog();
    }, 1200);
  }, [flushPersistAgentLog]);

  useEffect(
    () => () => {
      if (persistAgentLogTimerRef.current) clearTimeout(persistAgentLogTimerRef.current);
    },
    []
  );

  const bumpComposerQueue = useCallback(() => {
    setComposerQueueVersion((v) => v + 1);
  }, []);

  const activeComposerQueue = useMemo(() => {
    void composerQueueVersion;
    const tid = activeThreadId;
    if (!tid) return [];
    return composerQueueRef.current.get(tid) ?? [];
  }, [activeThreadId, composerQueueVersion]);

  const scheduleDrainComposerQueue = useCallback(() => {
    queueMicrotask(() => drainComposerQueueRef.current());
  }, []);

  const displayName = useMemo(() => {
    const e = user?.email;
    if (!e) return "there";
    return e.split("@")[0] ?? "there";
  }, [user?.email]);

  const selectedWorkspace = useMemo(
    () => workspaces.find((w) => w.id === selectedWorkspaceId) ?? null,
    [workspaces, selectedWorkspaceId]
  );

  const activeThread = useMemo(
    () => threads.find((th) => th.id === activeThreadId) ?? null,
    [threads, activeThreadId]
  );

  const threadComposerWorkspaceId = activeThread?.workspaceId;

  useEffect(() => {
    if (!activeThreadId) return;
    const wid =
      typeof threadComposerWorkspaceId === "string" && threadComposerWorkspaceId.trim()
        ? threadComposerWorkspaceId.trim()
        : null;
    setSelectedWorkspaceId(wid || null);
  }, [activeThreadId, threadComposerWorkspaceId]);

  useEffect(() => {
    const tid =
      typeof activeThread?.activeTaskId === "string" && activeThread.activeTaskId.trim()
        ? activeThread.activeTaskId.trim()
        : null;
    setActiveTaskId(tid);
  }, [activeThreadId, activeThread?.activeTaskId]);

  const messages = activeThread?.messages ?? [];
  const displayMessages = useMemo(
    () =>
      inferMissingMessageTimestamps(
        messages,
        activeThread?.conversationCreatedAt ?? activeThread?.updatedAt ?? 0,
        activeThread?.updatedAt ?? 0
      ),
    [messages, activeThread?.conversationCreatedAt, activeThread?.updatedAt]
  );
  const mode: ChatMode = activeThread?.mode ?? "agent";
  const model = activeThread?.model ?? "";
  const modelProvider = activeThread?.modelProvider;

  const threadContentKey = `${activeThreadId ?? ""}:${messages.length}:${hydrated}`;
  const { scrollContainerRef, messagesEndRef, scrollToBottom, showScrollFab } = useChatScroll({
    messageCount: messages.length,
    loading,
    activeThreadId,
    threadContentKey,
  });

  const userTurns = useMemo(() => buildTurnItems(messages, 40, (n) => t("chat:promptN", { n })), [messages, t]);
  const latestTurnId = useMemo(
    () => (activeThread ? latestUserMessageId(activeThread) : null),
    [activeThread, messages]
  );

  useEffect(() => {
    if (!activeThreadId) {
      setSelectedTurnId(null);
      return;
    }
    setSelectedTurnId(latestTurnId);
  }, [activeThreadId, latestTurnId]);

  const activityEntries = useMemo(() => {
    if (!activeThread) return [];
    return activityForTurn(activeThread, selectedTurnId);
  }, [activeThread, selectedTurnId]);

  const proposalSelectionMap = useMemo(
    () =>
      new Map(
        [...selectedProposalOptions.entries()].map(([id, v]) => [id, v.option.id])
      ),
    [selectedProposalOptions]
  );

  const activityLoading =
    loading && mode === "agent" && selectedTurnId === latestTurnId;

  const handleSelectTurn = useCallback((userMessageId: string) => {
    setSelectedTurnId(userMessageId);
    document.getElementById(`msg-${userMessageId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, []);

  const defaultSelectValue = useMemo(
    () => defaultModelCatalogSelectValue(modelRows),
    [modelRows]
  );
  const defaultModel = useMemo(() => {
    const p = parseModelCatalogSelection(defaultSelectValue);
    return p.modelId || modelRows[0]?.id || "";
  }, [defaultSelectValue, modelRows]);
  const modelSelectValue = useMemo(
    () => composerSelectValueForThread(modelRows, model, modelProvider, defaultSelectValue),
    [model, modelProvider, defaultSelectValue, modelRows]
  );

  const composerHeaderSummary = useMemo(() => {
    const projectLabel = selectedWorkspace?.name ?? t("chat:noProject");
    const modeLabel =
      mode === "agent" ? t("chat:replyModeAgent") : t("chat:replyModeChat");
    const row = modelRows.find((r) => modelCatalogSelectValue(r) === modelSelectValue);
    const modelLabel = row
      ? modelOptionLabel(row, modelCatalogAgentlayer)
      : model.trim() || t("chat:loadingModels");
    return `${projectLabel} · ${modeLabel} · ${modelLabel}`;
  }, [
    selectedWorkspace?.name,
    mode,
    modelRows,
    modelSelectValue,
    modelCatalogAgentlayer,
    model,
    t,
  ]);

  useEffect(() => {
    if (modelSelectValue.includes(":")) {
      lastModelSelectionRef.current = modelSelectValue;
    }
  }, [modelSelectValue]);

  useEffect(() => {
    setHydrated(false);
  }, [userId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const { rows, agentlayer } = await fetchModelCatalog();
        if (cancelled) return;
        setModelRows(rows);
        setModelCatalogAgentlayer(agentlayer);
        setModelsCatalogHint(formatModelCatalogHint(agentlayer, { excludeUnreachableProviderHints: true }));
      } catch {
        if (!cancelled) {
          setModelRows([]);
          setModelCatalogAgentlayer(null);
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

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const wsParam = selectedWorkspaceId ? selectedWorkspaceId : null;
      const r = await fetchSessionRuntime(auth, wsParam);
      if (!cancelled) setSessionRuntime(r);
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, selectedWorkspaceId]);

  useEffect(() => {
    if (!userId) return;
    setComposerHeaderCollapsed(getChatComposerHeaderCollapsed(userId));
    setProjectPanelOpen(getChatProjectPanelOpen(userId));
    setShowSubagentsInActivity(getShowSubagentsInActivity(userId));
  }, [userId]);

  const toggleComposerHeaderCollapsed = useCallback(() => {
    setComposerHeaderCollapsed((prev) => {
      const next = !prev;
      setChatComposerHeaderCollapsed(userId, next);
      return next;
    });
  }, [userId]);

  useEffect(() => {
    if (!accessToken) {
      setWorkspaces([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const r = await apiFetch("/v1/workspaces", auth);
        if (!r.ok || cancelled) return;
        const j = (await r.json()) as { workspaces?: WorkspaceApiRecord[] };
        if (cancelled) return;
        const list = j.workspaces ?? [];
        setWorkspaces(list);
        const wsFromUrl = (searchParams.get("workspace") || "").trim();
        setSelectedWorkspaceId((prev) => {
          if (wsFromUrl && list.some((w) => w.id === wsFromUrl)) return wsFromUrl;
          if (prev && list.some((w) => w.id === prev)) return prev;
          return null;
        });
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, auth, searchParams]);

  useEffect(() => {
    if (!dashboardChatId || !accessToken) {
      setDashboardChatTitle(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiFetch(`/v1/dashboards/${dashboardChatId}`, auth);
        const j = (await res.json()) as { dashboard?: { title?: string } };
        if (cancelled) return;
        if (res.ok && j.dashboard?.title) setDashboardChatTitle(j.dashboard.title);
        else setDashboardChatTitle(null);
      } catch {
        if (!cancelled) setDashboardChatTitle(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dashboardChatId, accessToken, auth]);

  const dashboardIdsInThreads = useMemo(() => {
    const s = new Set<string>();
    for (const t of threads) {
      if (t.dashboardId) s.add(t.dashboardId);
    }
    return [...s].sort().join(",");
  }, [threads]);

  useEffect(() => {
    if (!accessToken || !dashboardIdsInThreads) {
      setDashboardTitles({});
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const r = await apiFetch("/v1/dashboards", auth);
        if (!r.ok || cancelled) return;
        const j = (await r.json()) as { dashboards?: Array<{ id?: string; title?: string }> };
        const map: Record<string, string> = {};
        for (const w of j.dashboards || []) {
          if (w.id && typeof w.title === "string") map[w.id] = w.title;
        }
        if (!cancelled) setDashboardTitles(map);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, dashboardIdsInThreads, auth]);

  useEffect(() => {
    if (!accessToken || !userId) return;
    let cancelled = false;
    void (async () => {
      try {
        const listRaw = await fetchConversationList(auth);
        if (cancelled) return;
        if (listRaw.length === 0) {
          setThreads([]);
          setActiveThreadId(null);
          setSearchParams({}, { replace: true });
          setHydrated(true);
          return;
        }
        const mapped = listRaw.map((row) => mapListItemToThread(row as Record<string, unknown>));
        setThreads(mapped);
        const fromUrl = new URLSearchParams(window.location.search).get("c");
        let pick: string | null =
          fromUrl && mapped.some((x) => x.id === fromUrl) ? fromUrl : null;
        if (!pick) {
          const withMsgs = mapped.find((x) => threadMessageCount(x) > 0);
          pick = withMsgs?.id ?? mapped[0]?.id ?? null;
        }
        if (!pick) {
          setActiveThreadId(null);
          setHydrated(true);
          return;
        }
        setActiveThreadId(pick);
        const full = await fetchConversationDetail(auth, pick);
        if (cancelled) return;
        setThreads((prev) =>
          prev.map((th) => (th.id === full.id ? mergeServerThreadWithLocal(full, th) : th))
        );
        setSearchParams({ c: pick }, { replace: true });
        setHydrated(true);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : t("errors:loadChatsServerSyncFailed"));
          setHydrated(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, userId, auth, setSearchParams]);

  /** Prefill composer from Tools settings: `/chat?try=${encodeURIComponent(prompt)}` */
  useEffect(() => {
    const tryText = searchParams.get("try");
    if (!tryText?.trim() || !hydrated) return;
    let decoded = tryText;
    try {
      decoded = decodeURIComponent(tryText.replace(/\+/g, " "));
    } catch {
      /* use raw */
    }
    setDraft((prev) => (prev.trim() ? prev : decoded));
    setSearchParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.delete("try");
        return n;
      },
      { replace: true },
    );
  }, [hydrated, searchParams, setSearchParams]);

  useEffect(() => {
    const wsParam = (searchParams.get("workspace") || "").trim();
    if (!wsParam) return;
    workspaceDeepLinkRef.current = {
      workspaceId: wsParam,
      newSession: searchParams.get("new") === "1",
    };
  }, [searchParams]);

  useEffect(() => {
    const pending = workspaceDeepLinkRef.current;
    if (!pending || workspaces.length === 0 || !hydrated) return;
    if (!workspaces.some((w) => w.id === pending.workspaceId)) {
      workspaceDeepLinkRef.current = null;
      setSearchParams({}, { replace: true });
      setError(t("chat:workspaceFromLinkNotFound"));
      return;
    }
    const { workspaceId, newSession } = pending;
    workspaceDeepLinkRef.current = null;
    setSearchParams({}, { replace: true });
    setSelectedWorkspaceId(workspaceId);
    if (newSession) {
      void startNewChatRef.current(workspaceId);
      return;
    }
    const match = threads.find(
      (th) => th.workspaceId === workspaceId && (th.messageCount ?? th.messages.length) > 0
    );
    if (match) {
      setActiveThreadId(match.id);
      setSearchParams({ c: match.id }, { replace: true });
    }
  }, [workspaces, hydrated, threads, searchParams, setSearchParams, t]);

  useEffect(() => {
    if (mode !== "agent" && wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [mode]);

  useEffect(() => {
    if (!loading) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [loading]);

  const selectThread = useCallback(
    async (id: string) => {
      if (id === activeThreadId) return;
      setActiveThreadId(id);
      setSearchParams({ c: id });
      setError(null);
      try {
        const full = await fetchConversationDetail(auth, id);
        setThreads((prev) =>
          prev.map((th) => (th.id === id ? mergeServerThreadWithLocal(full, th) : th))
        );
      } catch {
        /* keep list row */
      }
    },
    [activeThreadId, auth, setSearchParams]
  );

  const patchThread = useCallback((id: string, patch: Partial<ChatThread>) => {
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== id) return t;
        const merged: ChatThread = { ...t, ...patch, updatedAt: Date.now() };
        if (patch.messages !== undefined) {
          merged.messageCount = patch.messages.length;
        }
        return merged;
      })
    );
  }, []);

  useEffect(() => {
    if (!activeThreadId || !modelsCatalogReady || modelRows.length === 0) return;
    const th = threads.find((x) => x.id === activeThreadId);
    if (!th?.model?.trim()) return;
    if (th.modelProvider && normalizeCatalogRoutingToken(th.modelProvider)) return;
    const routed = resolveSendModelRouting(modelRows, {
      modelSelectValue: composerSelectValueForThread(
        modelRows,
        th.model,
        th.modelProvider,
        defaultSelectValue
      ),
      defaultSelectValue,
      threadModel: th.model,
      threadProvider: th.modelProvider,
    });
    if (!routed) return;
    if (th.model === routed.model && th.modelProvider === routed.provider) return;
    lastModelSelectionRef.current = routed.selectValue;
    patchThread(activeThreadId, { model: routed.model, modelProvider: routed.provider });
  }, [activeThreadId, defaultSelectValue, modelsCatalogReady, modelRows, threads, patchThread]);

  const addPickedFiles = useCallback(async (files: FileList | File[] | null) => {
    if (!files?.length) return;
    try {
      const next = await filesToAttachments(files);
      setPendingAttachments((prev) => [...prev, ...next]);
    } catch {
      setError(t("chat:couldNotReadFile"));
    }
  }, []);

  const setMode = useCallback(
    (m: ChatMode) => {
      if (!activeThreadId) return;
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === activeThreadId ? { ...t, mode: m, updatedAt: Date.now() } : t
        );
        const th = next.find((x) => x.id === activeThreadId);
        if (th) void putConversation(auth, th).catch(() => {});
        return next;
      });
    },
    [activeThreadId, auth]
  );

  const setModel = useCallback(
    (raw: string) => {
      if (!activeThreadId) return;
      lastModelSelectionRef.current = raw;
      const { model: mid, modelProvider: prov } = applyModelCatalogSelection(raw, modelRows);
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === activeThreadId
            ? { ...t, model: mid, modelProvider: prov, updatedAt: Date.now() }
            : t
        );
        const th = next.find((x) => x.id === activeThreadId);
        if (th) void putConversation(auth, th).catch(() => {});
        return next;
      });
    },
    [activeThreadId, auth, modelRows]
  );

  const startNewChatRef = useRef<(workspaceIdOverride?: string | null) => Promise<void>>(
    async () => {}
  );
  const workspaceDeepLinkRef = useRef<{ workspaceId: string; newSession: boolean } | null>(null);

  const setComposerWorkspace = useCallback(
    (wsId: string | null) => {
      if (!activeThreadId) return;
      if (wsId) {
        const thread = threads.find((x) => x.id === activeThreadId);
        const msgCount = thread?.messageCount ?? thread?.messages.length ?? 0;
        const prevWs = typeof thread?.workspaceId === "string" ? thread.workspaceId : null;
        if (shouldIsolateWorkspaceThread(msgCount, prevWs, wsId)) {
          const wsName = workspaces.find((w) => w.id === wsId)?.name ?? wsId;
          if (confirmNewChatForWorkspace(wsName)) {
            void startNewChatRef.current(wsId);
            return;
          }
        }
      }
      setWorkspaceScopeHint(null);
      setSelectedWorkspaceId(wsId);
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === activeThreadId ? { ...t, workspaceId: wsId, updatedAt: Date.now() } : t
        );
        const th = next.find((x) => x.id === activeThreadId);
        if (th) void putConversation(auth, th).catch(() => {});
        return next;
      });
    },
    [activeThreadId, auth, threads, workspaces]
  );

  const assistantStreamOffset = useCallback((): number => {
    return Math.max(0, streamDeltaAccRef.current.length);
  }, []);

  const appendAgentLine = useCallback(
    (
      kind: string,
      text: string,
      extras?: Omit<AgentTimelineEntry, "id" | "kind" | "text">
    ) => {
      const tid = activeThreadIdRef.current;
      if (!tid) return;
      setThreads((prev) =>
        prev.map((t) => {
          if (t.id !== tid) return t;
          const next = appendTimelineEntry(t.agentLog ?? [], {
            kind,
            text,
            ...extras,
          });
          return { ...t, agentLog: next, updatedAt: Date.now() };
        })
      );
      schedulePersistAgentLog();
    },
    [schedulePersistAgentLog]
  );

  const handleSecretSaved = useCallback((promptId: string, serviceKey: string) => {
    const tid = activeThreadIdRef.current;
    if (tid) {
      setThreads((prev) =>
        prev.map((t) => {
          if (t.id !== tid) return t;
          return { ...t, ...markSecretPromptSaved(t, promptId), updatedAt: Date.now() };
        })
      );
    }
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "secret_saved",
          prompt_id: promptId,
          service_key: serviceKey,
          ok: true,
        })
      );
    }
  }, []);

  const handleIndexActivity = useCallback(
    (ev: IndexActivityEvent) => {
      const { kind, text, extras } = indexActivityToTimeline(ev);
      const base = extras as Omit<AgentTimelineEntry, "id" | "kind" | "text">;
      if (kind === "index_start") {
        appendAgentLine(kind, text, { ...base, streamOffset: assistantStreamOffset() });
      } else {
        appendAgentLine(kind, text, base);
      }
    },
    [appendAgentLine, assistantStreamOffset]
  );

  const applyInFlightRestore = useCallback(
    (snapshot: InFlightTurnSnapshot) => {
      const tid = snapshot.threadId;
      if (snapshot.rewindUserMessage) {
        setDraft(snapshot.draft);
        setPendingAttachments([...snapshot.attachments]);
      }
      const priorUsers = snapshot.priorMessages.filter((m) => m.role === "user" && m.id);
      setSelectedTurnId(
        priorUsers[priorUsers.length - 1]?.id ?? snapshot.userMsgId ?? null
      );

      setThreads((prev) => {
        const next = prev.map((th) => {
          if (th.id !== tid) return th;
          const messages = snapshot.rewindUserMessage
            ? [...snapshot.priorMessages]
            : stripTrailingAssistantsAfterLastUser(
                th.messages.length ? th.messages : snapshot.priorMessages
              );
          const updated: ChatThread = {
            ...th,
            messages,
            title: snapshot.priorTitle,
            agentLog: snapshot.rewindUserMessage ? [...snapshot.priorAgentLog] : [],
            turnLogs: snapshot.rewindUserMessage
              ? [...snapshot.priorTurnLogs]
              : th.turnLogs,
            messageCount: messages.length,
            updatedAt: Date.now(),
          };
          void putConversation(auth, updated).catch(() => {});
          return updated;
        });
        return next;
      });
    },
    [auth]
  );

  const runChatHttp = useCallback(async (queued?: QueuedComposerMessage, opts?: SendTurnOptions) => {
    if (!accessToken || !activeThreadId) return;
    const tid = activeThreadId;
    const thread = threads.find((x) => x.id === tid);
    const routed = resolveSendModelRouting(modelRows, {
      lastSelection: lastModelSelectionRef.current,
      modelSelectValue,
      defaultSelectValue,
      threadModel: (thread?.model || defaultModel).trim(),
      threadProvider: thread?.modelProvider,
    });
    if (!thread || !routed) {
      setError(t("errors:resolveModelProviderFailed"));
      return;
    }
    lastModelSelectionRef.current = routed.selectValue;

    const resendUserMsgId = opts?.resendUserMsgId?.trim() || null;
    const isResend = Boolean(resendUserMsgId);
    let sendDraft: string;
    let sendAttachments: PendingAttachment[];
    let userMsgId: string;
    let nextMessages: UiMessage[];
    let nextTitle: string;
    let archivePatch: Pick<ChatThread, "turnLogs" | "agentLog"> = {};

    if (isResend && resendUserMsgId) {
      const userIdx = thread.messages.findIndex(
        (m) => m.id === resendUserMsgId && m.role === "user"
      );
      if (userIdx < 0) return;
      const userMsg = thread.messages[userIdx]!;
      const composer = userMessageToComposerState(userMsg.content);
      sendDraft = composer.draft;
      sendAttachments = composer.attachments;
      userMsgId = resendUserMsgId;
      nextMessages = thread.messages.slice(0, userIdx + 1);
      nextTitle = thread.title;
      archivePatch = {
        agentLog: [],
        turnLogs: (thread.turnLogs ?? []).filter((tl) => tl.userMessageId !== userMsgId),
      };
    } else {
      sendDraft = queued?.draft ?? draft;
      sendAttachments = queued?.attachments ?? pendingAttachments;
      const userContent = buildUserMessageContent(sendDraft, sendAttachments);
      if (!userContent) return;
      const firstUser = thread.messages.length === 0;
      userMsgId = newMessageId();
      nextMessages = [
        ...thread.messages,
        { role: "user", content: userContent, id: userMsgId, createdAt: Date.now() },
      ];
      nextTitle = firstUser ? titleFromFirstMessage(userContent) : thread.title;
      archivePatch = archiveTurnBeforeNewPrompt(thread);
    }

    if (!isResend && (thread.agentLog?.length ?? 0) > 0) {
      void putConversation(auth, {
        ...thread,
        messages: nextMessages,
        ...archivePatch,
        title: nextTitle,
        model: routed.model,
        modelProvider: routed.provider,
        messageCount: nextMessages.length,
        updatedAt: Date.now(),
      }).catch(() => {});
    }

    const userContentForApi = buildUserMessageContent(sendDraft, sendAttachments);
    if (!userContentForApi) return;

    inFlightTurnRef.current = {
      threadId: tid,
      userMsgId,
      draft: sendDraft,
      attachments: [...sendAttachments],
      priorMessages: isResend ? [...nextMessages] : [...thread.messages],
      priorTitle: thread.title,
      priorAgentLog: [...(thread.agentLog ?? [])],
      priorTurnLogs: [...(thread.turnLogs ?? [])],
      rewindUserMessage: !isResend,
    };
    skipQueueDrainOnFinishRef.current = false;

    setError(null);
    setLoading(true);
    setTokenUsage(emptyTokenUsage());
    patchThread(tid, {
      messages: nextMessages,
      ...archivePatch,
      title: nextTitle,
      model: routed.model,
      modelProvider: routed.provider,
    });
    setSelectedTurnId(userMsgId);
    if (!queued && !isResend) {
      setDraft("");
      setPendingAttachments([]);
    }

    chatAbortControllerRef.current?.abort();
    const chatAbort = new AbortController();
    chatAbortControllerRef.current = chatAbort;

    try {
      const disabledTools = getDisabledToolNames();
      const payload = {
        model: routed.model,
        messages: nextMessages.map((m) => ({ role: m.role, content: toApiContent(m.content) })),
        stream: true,
        agent_plain_completion: true,
        stream_options: { include_usage: true },
        ...agentDashboardPayload,
        ...(disabledTools.length ? { agent_disabled_tools: disabledTools } : {}),
        agent_model_catalog_owned_by: routed.provider,
      };
      const res = await apiFetch("/v1/chat/completions", auth, {
        method: "POST",
        body: JSON.stringify(payload),
        signal: chatAbort.signal,
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const errBody = (await res.json()) as { detail?: unknown };
          if (errBody.detail != null) detail = String(errBody.detail);
        } catch {
          /* ignore */
        }
        setError(detail);
        return;
      }
      const ctype = (res.headers.get("content-type") || "").toLowerCase();
      if (ctype.includes("text/event-stream")) {
        let acc = "";
        try {
          for await (const chunk of streamOpenAiChatChunks(res)) {
            if (chunk.kind === "usage") {
              setTokenUsage((prev) => addUsageTotals(prev, chunk.usage));
              continue;
            }
            acc += chunk.text;
            setThreads((prev) =>
              prev.map((th) => {
                if (th.id !== tid) return th;
                const last = th.messages[th.messages.length - 1];
                return {
                  ...th,
                  messages: [...nextMessages, assistantMessage(acc, last)],
                  messageCount: nextMessages.length + 1,
                  updatedAt: Date.now(),
                };
              })
            );
          }
        } catch (streamErr) {
          const aborted =
            streamErr instanceof DOMException && streamErr.name === "AbortError";
          if (!aborted) {
            setError(streamErr instanceof Error ? streamErr.message : String(streamErr));
          }
          return;
        }
        inFlightTurnRef.current = null;
        const reply = acc.trim() || "(empty)";
        setThreads((prev) => {
          const next = prev.map((th) => {
            if (th.id !== tid) return th;
            const last = th.messages[th.messages.length - 1];
            const updated: ChatThread = {
              ...th,
              messages: [...nextMessages, assistantMessage(reply, last)],
              messageCount: nextMessages.length + 1,
              updatedAt: Date.now(),
            };
            void putConversation(auth, updated).catch(() => {});
            return updated;
          });
          return next;
        });
        return;
      }
      const data = await res.json();
      if (data && typeof data === "object" && "agentlayer_context" in data) {
        const ctx = (data as { agentlayer_context?: unknown }).agentlayer_context;
        if (ctx && typeof ctx === "object") {
          setChatContextMeta(ctx as ChatContextMeta);
        }
      }
      if (data && typeof data === "object" && "usage" in data) {
        setTokenUsage((prev) => addUsageTotals(prev, (data as { usage?: unknown }).usage));
      }
      inFlightTurnRef.current = null;
      const content = assistantFromCompletion(data);
      setThreads((prev) => {
        const next = prev.map((th) => {
          if (th.id !== tid) return th;
          const updated: ChatThread = {
            ...th,
            messages: [
              ...th.messages,
              assistantMessage(content || "(empty)", th.messages[th.messages.length - 1]),
            ],
            messageCount: th.messages.length + 1,
            updatedAt: Date.now(),
          };
          void putConversation(auth, updated).catch(() => {});
          return updated;
        });
        return next;
      });
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      if (!aborted) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (chatAbortControllerRef.current === chatAbort) {
        chatAbortControllerRef.current = null;
      }
      setLoading(false);
      if (!skipQueueDrainOnFinishRef.current) {
        scheduleDrainComposerQueue();
      } else {
        skipQueueDrainOnFinishRef.current = false;
      }
    }
  }, [
    accessToken,
    activeThreadId,
    agentDashboardPayload,
    auth,
    defaultModel,
    draft,
    modelRows,
    modelSelectValue,
    pendingAttachments,
    patchThread,
    scheduleDrainComposerQueue,
    threads,
  ]);
  runChatHttpRef.current = runChatHttp;

  const ensureAgentWs = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const tok = accessToken;
      if (!tok) {
        reject(new Error(t("errors:notSignedIn")));
        return;
      }
      const existing = wsRef.current;
      if (existing?.readyState === WebSocket.OPEN) {
        resolve(existing);
        return;
      }
      if (existing) {
        existing.close();
        wsRef.current = null;
      }
      const ws = new WebSocket(wsUrl(tok));
      ws.onopen = () => {
        wsRef.current = ws;
        ws.onmessage = (ev) => agentHandlerRef.current(ev);
        resolve(ws);
      };
      ws.onerror = () => reject(new Error(t("errors:websocketFailed")));
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        agentTurnFinishRef.current?.();
      };
    });
  }, [accessToken]);

  const runAgentWs = useCallback(async (queued?: QueuedComposerMessage, opts?: SendTurnOptions) => {
    if (!accessToken || !activeThreadId) return;
    const tid = activeThreadId;
    const thread = threads.find((x) => x.id === tid);
    const routed = resolveSendModelRouting(modelRows, {
      lastSelection: lastModelSelectionRef.current,
      modelSelectValue,
      defaultSelectValue,
      threadModel: (thread?.model || defaultModel).trim(),
      threadProvider: thread?.modelProvider,
    });
    if (!thread || !routed) {
      setError(t("errors:resolveModelProviderFailed"));
      return;
    }
    lastModelSelectionRef.current = routed.selectValue;

    const resendUserMsgId = opts?.resendUserMsgId?.trim() || null;
    const isResend = Boolean(resendUserMsgId);
    let sendDraft: string;
    let sendAttachments: PendingAttachment[];
    let userMsgId: string;
    let nextMessages: UiMessage[];
    let nextTitle: string;
    let archivePatch: Pick<ChatThread, "turnLogs" | "agentLog"> = {};

    if (isResend && resendUserMsgId) {
      const userIdx = thread.messages.findIndex(
        (m) => m.id === resendUserMsgId && m.role === "user"
      );
      if (userIdx < 0) return;
      const userMsg = thread.messages[userIdx]!;
      const composer = userMessageToComposerState(userMsg.content);
      sendDraft = composer.draft;
      sendAttachments = composer.attachments;
      userMsgId = resendUserMsgId;
      nextMessages = thread.messages.slice(0, userIdx + 1);
      nextTitle = thread.title;
      archivePatch = {
        agentLog: [],
        turnLogs: (thread.turnLogs ?? []).filter((tl) => tl.userMessageId !== userMsgId),
      };
    } else {
      sendDraft = queued?.draft ?? draft;
      sendAttachments = queued?.attachments ?? pendingAttachments;
      const userContent = buildUserMessageContent(sendDraft, sendAttachments);
      if (!userContent) return;
      const firstUser = thread.messages.length === 0;
      userMsgId = newMessageId();
      nextMessages = [
        ...thread.messages,
        { role: "user", content: userContent, id: userMsgId, createdAt: Date.now() },
      ];
      nextTitle = firstUser ? titleFromFirstMessage(userContent) : thread.title;
      archivePatch = archiveTurnBeforeNewPrompt(thread);
    }

    if (!isResend && (thread.agentLog?.length ?? 0) > 0) {
      void putConversation(auth, {
        ...thread,
        messages: nextMessages,
        ...archivePatch,
        title: nextTitle,
        model: routed.model,
        modelProvider: routed.provider,
        messageCount: nextMessages.length,
        updatedAt: Date.now(),
      }).catch(() => {});
    }

    if (!buildUserMessageContent(sendDraft, sendAttachments)) return;

    inFlightTurnRef.current = {
      threadId: tid,
      userMsgId,
      draft: sendDraft,
      attachments: [...sendAttachments],
      priorMessages: isResend ? [...nextMessages] : [...thread.messages],
      priorTitle: thread.title,
      priorAgentLog: [...(thread.agentLog ?? [])],
      priorTurnLogs: [...(thread.turnLogs ?? [])],
      rewindUserMessage: !isResend,
    };
    skipQueueDrainOnFinishRef.current = false;

    setError(null);
    setLoading(true);
    setTokenUsage(emptyTokenUsage());
    patchThread(tid, {
      messages: nextMessages,
      ...archivePatch,
      title: nextTitle,
      model: routed.model,
      modelProvider: routed.provider,
    });
    setSelectedTurnId(userMsgId);
    agentTurnBaselineRef.current = nextMessages;
    streamDeltaAccRef.current = "";
    agentStreamEnabledThisTurnRef.current = getAgentStreamLlm();
    if (!queued && !isResend) {
      setDraft("");
      setPendingAttachments([]);
    }

    cancelAgentTurnRef.current = false;
    agentTurnFinishRef.current = null;

    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      agentTurnFinishRef.current = null;
      if (persistAgentLogTimerRef.current) {
        clearTimeout(persistAgentLogTimerRef.current);
        persistAgentLogTimerRef.current = null;
      }
      setLoading(false);
      const skipDrain = skipQueueDrainOnFinishRef.current;
      if (skipDrain) {
        skipQueueDrainOnFinishRef.current = false;
      } else {
        scheduleDrainComposerQueue();
      }
      const id = activeThreadIdRef.current;
      if (id && !skipDrain) {
        setThreads((prev) => {
          const next = prev.map((th) => {
            if (th.id !== id) return th;
            const messages = stripTrailingEmptyAssistantMessages(th.messages);
            if (messages.length === th.messages.length) return th;
            return {
              ...th,
              messages,
              messageCount: messages.length,
              updatedAt: Date.now(),
            };
          });
          const th = next.find((x) => x.id === id);
          if (th) void putConversation(auth, th).catch(() => {});
          return next;
        });
      }
    };
    agentTurnFinishRef.current = finish;

    agentHandlerRef.current = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        const typ = msg.type;
        if (typ === "pong") return;
        if (typ === "error") {
          setError(typeof msg.detail === "string" ? msg.detail : t("errors:agentError"));
          finish();
          return;
        }
        if (typ === "chat.completion") {
          if (msg.error) {
            setError(typeof msg.detail === "string" ? msg.detail : t("chat:cancelledOrFailed"));
            finish();
            return;
          }
          const data = msg.data;
          if (data && typeof data === "object" && "usage" in data) {
            setTokenUsage((prev) => addUsageTotals(prev, (data as { usage?: unknown }).usage));
          }
          const acc = streamDeltaAccRef.current.trim();
          const fromApi = assistantFromCompletion(data);
          const content =
            agentStreamEnabledThisTurnRef.current && acc.length > 0 ? acc : fromApi;
          const id = activeThreadIdRef.current;
          if (id && content.trim()) {
            inFlightTurnRef.current = null;
            setThreads((prev) => {
              const next = prev.map((th) => {
                if (th.id !== id) return th;
                const prevMsgs = th.messages;
                const last = prevMsgs[prevMsgs.length - 1];
                const replaceLastAssistant =
                  agentStreamEnabledThisTurnRef.current &&
                  last?.role === "assistant";
                const messages: UiMessage[] = replaceLastAssistant
                  ? [...prevMsgs.slice(0, -1), assistantMessage(content, last)]
                  : [...prevMsgs, assistantMessage(content)];
                const updated: ChatThread = {
                  ...th,
                  messages,
                  messageCount: messages.length,
                  updatedAt: Date.now(),
                };
                void putConversation(auth, updated).catch(() => {});
                return updated;
              });
              return next;
            });
          } else {
            inFlightTurnRef.current = null;
          }
          finish();
          return;
        }
        if (typ === "agent.session") {
          const em = msg.effective_model != null ? String(msg.effective_model) : "";
          const mr = msg.model_resolution != null ? String(msg.model_resolution) : "";
          appendAgentLine("session", [em && `model: ${em}`, mr && `(${mr})`].filter(Boolean).join(" "));
          if (msg.context && typeof msg.context === "object") {
            setChatContextMeta(msg.context as ChatContextMeta);
          }
          if (msg.agent_auto_routed === true && msg.effective_agent_id != null) {
            const aid = String(msg.effective_agent_id).trim();
            if (aid) {
              const tid = activeThreadIdRef.current;
              if (tid) {
                setThreads((prev) => {
                  const next = prev.map((th) =>
                    th.id === tid ? { ...th, agentId: aid, updatedAt: Date.now() } : th
                  );
                  const th = next.find((x) => x.id === tid);
                  if (th) void putConversation(auth, th).catch(() => {});
                  return next;
                });
              }
            }
          }
          if (
            (msg.workspace_auto_created === true || msg.workspace_bound === true) &&
            msg.workspace_id != null
          ) {
            const wid = String(msg.workspace_id).trim();
            if (wid) {
              setSelectedWorkspaceId(wid);
              const tid = activeThreadIdRef.current;
              if (tid) {
                const th0 = threads.find((x) => x.id === tid);
                const msgCount = th0?.messageCount ?? th0?.messages.length ?? 0;
                const wsName = workspaces.find((w) => w.id === wid)?.name ?? "project";
                if (msg.workspace_bound === true && msgCount > 2) {
                  setWorkspaceScopeHint(
                    t("chat:workspaceBoundHint", { name: wsName })
                  );
                }
                setThreads((prev) => {
                  const next = prev.map((th) =>
                    th.id === tid ? { ...th, workspaceId: wid, updatedAt: Date.now() } : th
                  );
                  const th = next.find((x) => x.id === tid);
                  if (th) void putConversation(auth, th).catch(() => {});
                  return next;
                });
              }
            }
          }
          return;
        }
        if (typ === "agent.llm_round_start") {
          const r = msg.round != null ? Number(msg.round) : 0;
          if (agentStreamEnabledThisTurnRef.current && r > 1) {
            streamDeltaAccRef.current += "\n\n";
            const tid0 = activeThreadIdRef.current;
            const base0 = agentTurnBaselineRef.current;
            if (tid0 && base0) {
              const streamed = messagesWithStreamedAssistant(
                base0,
                streamDeltaAccRef.current
              );
              if (streamed.length > base0.length) {
                setThreads((prev) =>
                  prev.map((th) =>
                    th.id === tid0
                      ? {
                          ...th,
                          messages: streamed,
                          messageCount: streamed.length,
                          updatedAt: Date.now(),
                        }
                      : th
                  )
                );
              }
            }
          }
          const rLabel = msg.round != null ? `round ${msg.round}` : "round";
          appendAgentLine("llm", `${rLabel} (start)`);
          return;
        }
        if (typ === "agent.llm_delta") {
          const tid0 = activeThreadIdRef.current;
          const base0 = agentTurnBaselineRef.current;
          if (!tid0 || !base0 || !agentStreamEnabledThisTurnRef.current) return;
          const d = msg.delta != null ? String(msg.delta) : "";
          if (!d) return;
          streamDeltaAccRef.current += d;
          if (!streamDeltaAccRef.current.trim()) return;
          const streamed = messagesWithStreamedAssistant(
            base0,
            streamDeltaAccRef.current
          );
          setThreads((prev) =>
            prev.map((th) =>
              th.id === tid0
                ? {
                    ...th,
                    messages: streamed,
                    messageCount: streamed.length,
                    updatedAt: Date.now(),
                  }
                : th
            )
          );
          return;
        }
        if (typ === "agent.llm_round") {
          const r = msg.round != null ? `round ${msg.round}` : "round";
          const ex =
            msg.content_excerpt != null ? String(msg.content_excerpt).slice(0, 200) : "";
          appendAgentLine("llm", `${r}${ex ? ` — ${ex}` : ""}`);
          if (msg.usage != null) {
            setTokenUsage((prev) => addUsageTotals(prev, msg.usage));
          }
          return;
        }
        if (
          handleSubagentWsEvent(
            typ,
            msg as Record<string, unknown>,
            appendAgentLine,
            subagentStartTimesRef.current,
            assistantStreamOffset
          )
        ) {
          return;
        }
        if (typ === "agent.secret_prompt") {
          const promptId = String(msg.prompt_id ?? "").trim();
          const serviceKey = String(msg.service_key ?? "")
            .trim()
            .toLowerCase();
          if (!promptId || !serviceKey) return;
          const rawFields = msg.fields;
          const fields = Array.isArray(rawFields)
            ? rawFields
                .filter((f): f is Record<string, unknown> => !!f && typeof f === "object")
                .map((f) => ({
                  name: String(f.name ?? ""),
                  label: f.label != null ? String(f.label) : undefined,
                  type: f.type != null ? String(f.type) : undefined,
                  required: f.required === true,
                }))
                .filter((f) => f.name.length > 0)
            : [];
          appendAgentLine("secret_prompt", serviceKey, {
            streamOffset: assistantStreamOffset(),
            secretPrompt: {
              promptId,
              serviceKey,
              mode: "authenticated",
              title: msg.title != null ? String(msg.title) : undefined,
              help: msg.help != null ? String(msg.help) : undefined,
              reason: msg.reason != null ? String(msg.reason) : undefined,
              fields,
              status: "pending",
            },
          });
          return;
        }
        if (typ === "agent.tool_start") {
          const toolName = String(msg.name ?? "tool");
          const summary = typeof msg.summary === "string" ? msg.summary.trim() : undefined;
          toolStartTimesRef.current.set(toolName, Date.now());
          appendAgentLine("tool_start", summary ? formatToolStepLabel(toolName, summary) : `→ ${toolName}`, {
            toolName,
            toolSummary: summary,
            streamOffset: assistantStreamOffset(),
          });
          return;
        }
        if (typ === "agent.tool_done") {
          const n = msg.name != null ? String(msg.name) : "tool";
          const ch = msg.result_chars != null ? Number(msg.result_chars) : undefined;
          let durationMs = msg.duration_ms != null ? Number(msg.duration_ms) : null;
          if (durationMs == null || durationMs < 0) {
            const startTime = toolStartTimesRef.current.get(n);
            if (startTime != null) {
              durationMs = Date.now() - startTime;
              toolStartTimesRef.current.delete(n);
            }
          }
          const parts: string[] = [];
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
          appendAgentLine("tool_done", `${n}${parts.length ? ` (${parts.join(", ")})` : ""}`, {
            toolName: n,
            durationMs: durationMs ?? undefined,
            resultChars: ch,
          });
          return;
        }
        if (typ === "agent.step_wait") {
          appendAgentLine("wait", t("chat:pausedStepMode"));
          return;
        }
        if (typ === "agent.done" || typ === "agent.aborted" || typ === "agent.cancelled") {
          appendAgentLine(String(typ), String(msg.detail ?? ""));
          if (typ === "agent.done") setProjectTreeRefreshKey((k) => k + 1);
          return;
        }
        appendAgentLine(String(typ ?? "event"), JSON.stringify(msg).slice(0, 300));
      } catch {
        setError(t("chat:invalidWebsocketMessage"));
        finish();
      }
    };

    try {
      const ws = await ensureAgentWs();
      if (cancelAgentTurnRef.current) {
        cancelAgentTurnRef.current = false;
        finish();
        return;
      }
      const disabledTools = getDisabledToolNames();
      ws.send(
        JSON.stringify({
          type: "chat",
          body: {
            model: routed.model,
            messages: nextMessages.map((m) => ({ role: m.role, content: toApiContent(m.content) })),
            agent_id: composerAgentId,
            ...(selectedWorkspaceId ? { workspace_id: selectedWorkspaceId } : {}),
            ...(activeThreadId ? { conversation_id: activeThreadId } : {}),
            ...(activeTaskId ? { agent_active_task_id: activeTaskId } : {}),
            ...agentDashboardPayload,
            ...(disabledTools.length ? { agent_disabled_tools: disabledTools } : {}),
            agent_model_catalog_owned_by: routed.provider,
            ...(getAgentStreamLlm() ? { agent_stream_llm: true } : {}),
          },
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
      scheduleDrainComposerQueue();
    }
  }, [
    accessToken,
    activeThreadId,
    agentDashboardPayload,
    appendAgentLine,
    auth,
    defaultModel,
    draft,
    ensureAgentWs,
    modelRows,
    modelSelectValue,
    patchThread,
    pendingAttachments,
    composerAgentId,
    selectedWorkspaceId,
    scheduleDrainComposerQueue,
    threads,
  ]);
  runAgentWsRef.current = runAgentWs;

  const drainComposerQueue = useCallback(() => {
    const tid = activeThreadIdRef.current;
    if (!tid) return;
    const q = composerQueueRef.current.get(tid);
    if (!q?.length) return;
    const next = q.shift();
    if (!q.length) composerQueueRef.current.delete(tid);
    else composerQueueRef.current.set(tid, q);
    bumpComposerQueue();
    if (!next) return;
    const thread = threadsRef.current.find((x) => x.id === tid);
    const chatMode = thread?.mode ?? "agent";
    void (chatMode === "chat" ? runChatHttpRef.current(next) : runAgentWsRef.current(next));
  }, [bumpComposerQueue]);
  drainComposerQueueRef.current = drainComposerQueue;

  const onQueue = useCallback(() => {
    const tid = activeThreadId;
    if (!tid) return;
    const userContent = buildUserMessageContent(draft, pendingAttachments);
    if (!userContent) return;
    const item: QueuedComposerMessage = {
      id: newMessageId(),
      draft,
      attachments: [...pendingAttachments],
    };
    const q = composerQueueRef.current.get(tid) ?? [];
    q.push(item);
    composerQueueRef.current.set(tid, q);
    bumpComposerQueue();
    setDraft("");
    setPendingAttachments([]);
  }, [activeThreadId, bumpComposerQueue, draft, pendingAttachments]);

  const removeFromComposerQueue = useCallback(
    (itemId: string) => {
      const tid = activeThreadId;
      if (!tid) return;
      const q = composerQueueRef.current.get(tid);
      if (!q?.length) return;
      const next = q.filter((item) => item.id !== itemId);
      if (next.length) composerQueueRef.current.set(tid, next);
      else composerQueueRef.current.delete(tid);
      bumpComposerQueue();
    },
    [activeThreadId, bumpComposerQueue]
  );

  const handleSelectProposalOption = useCallback(
    (proposal: Proposal, option: ProposalOption) => {
      setSelectedProposalOptions((prev) => {
        const next = new Map(prev);
        next.set(proposal.id, { proposal, option });
        return next;
      });
      setDraft(formatOptionSelection(proposal, option));
      setTimeout(() => {
        void runAgentWs();
      }, 100);
    },
    [runAgentWs]
  );

  const onSend = () => {
    void (mode === "chat" ? runChatHttp() : runAgentWs());
  };

  const abortInFlightTurn = useCallback(() => {
    chatAbortControllerRef.current?.abort();
    chatAbortControllerRef.current = null;
    cancelAgentTurnRef.current = true;
    skipQueueDrainOnFinishRef.current = true;

    const snapshot = inFlightTurnRef.current;
    if (snapshot && snapshot.threadId === activeThreadIdRef.current) {
      applyInFlightRestore(snapshot);
      inFlightTurnRef.current = null;
    }

    agentTurnFinishRef.current?.();
    agentTurnFinishRef.current = null;
    setLoading(false);
    const w = wsRef.current;
    if (w?.readyState === WebSocket.OPEN) {
      try {
        w.send(JSON.stringify({ type: "cancel" }));
      } catch {
        /* ignore */
      }
    }
  }, [applyInFlightRestore]);

  const onCancelInFlight = useCallback(() => {
    abortInFlightTurn();
  }, [abortInFlightTurn]);

  const copyUserMessage = useCallback(
    async (content: string) => {
      try {
        await navigator.clipboard.writeText(userMessagePlainText(content));
      } catch {
        setError(t("chat:messageCopyFailed"));
      }
    },
    [t]
  );

  const retryUserTurn = useCallback(
    (userMsgId: string) => {
      if (loading || !activeThreadId) return;
      const thread = threads.find((x) => x.id === activeThreadId);
      if (!thread) return;
      const userIdx = thread.messages.findIndex(
        (m) => m.id === userMsgId && m.role === "user"
      );
      if (userIdx < 0) return;
      if (userIdx !== lastUserMessageIndex(thread.messages)) return;
      void (thread.mode === "chat"
        ? runChatHttpRef.current(undefined, { resendUserMsgId: userMsgId })
        : runAgentWsRef.current(undefined, { resendUserMsgId: userMsgId }));
    },
    [activeThreadId, loading, threads]
  );

  const requestDeleteProject = useCallback(
    (ws: WorkspaceApiRecord) => {
      if (isAgentlayerSelfWorkspace(ws)) {
        setError(t("chat:deleteProjectSelfForbidden"));
        return;
      }
      if (ws.access_role === "viewer") {
        setError(t("chat:deleteProjectViewerForbidden"));
        return;
      }
      setDeleteProjectTarget(ws);
    },
    [t]
  );

  const confirmDeleteProject = useCallback(async () => {
    const ws = deleteProjectTarget;
    if (!ws) return;
    setDeletingProject(true);
    try {
      await deleteWorkspaceApi(auth, ws.id);
      setWorkspaces((prev) => prev.filter((w) => w.id !== ws.id));
      if (selectedWorkspaceId === ws.id) {
        setSelectedWorkspaceId(null);
        if (activeThreadId) {
          setComposerWorkspace(null);
        }
      }
      setThreads((prev) =>
        prev.map((th) =>
          th.workspaceId === ws.id ? { ...th, workspaceId: null, updatedAt: Date.now() } : th
        )
      );
      setDeleteProjectTarget(null);
      setProjectPanelOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("chat:deleteProjectFailed"));
    } finally {
      setDeletingProject(false);
    }
  }, [
    activeThreadId,
    auth,
    deleteProjectTarget,
    selectedWorkspaceId,
    setComposerWorkspace,
    t,
  ]);

  const startNewChat = useCallback(
    async (workspaceIdOverride?: string | null) => {
      abortInFlightTurn();
      try {
        const defaultProv = parseModelCatalogSelection(defaultSelectValue).provider;
        const ws = workspaceIdOverride !== undefined ? workspaceIdOverride : null;
        const newThread = await createConversation(auth, {
          title: NEW_CHAT_TITLE,
          mode: "agent",
          model: defaultModel,
          messages: [],
          agent_log: serializeAgentLogPayload({ agentLog: [], turnLogs: [] }),
          agent_id: "general",
          workspace_id: ws,
          model_catalog_owned_by: defaultProv ?? null,
        });
        setThreads((prev) => [newThread, ...prev]);
        setActiveThreadId(newThread.id);
        setSearchParams({ c: newThread.id });
        setSelectedWorkspaceId(ws);
        setDraft("");
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [abortInFlightTurn, auth, defaultModel, defaultSelectValue, setSearchParams]
  );
  startNewChatRef.current = startNewChat;

  const deleteThread = async (id: string) => {
    if (!confirm(t("chat:deleteConfirm"))) return;
    try {
      await deleteConversationApi(auth, id);
      setThreads((prev) => {
        const next = prev.filter((t) => t.id !== id);
        if (next.length === 0) {
          setActiveThreadId(null);
          setSearchParams({}, { replace: true });
          return [];
        }
        if (id === activeThreadId) {
          const n = next[0];
          setActiveThreadId(n.id);
          setSearchParams({ c: n.id });
        }
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const renameThread = (id: string) => {
    const thread = threads.find((x) => x.id === id);
    if (!thread) return;
    const next = window.prompt(t("chat:renamePrompt"), thread.title);
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed) return;
    patchThread(id, { title: trimmed });
    void putConversation(auth, { ...thread, title: trimmed }).catch(() => {});
  };

  const shareThread = async (thread: ChatThread) => {
    const url = `${window.location.origin}/app/chat?c=${encodeURIComponent(thread.id)}`;
    try {
      await navigator.clipboard.writeText(url + "\n\n" + exportThreadJson(thread));
    } catch {
      setError(t("errors:copyFailed"));
    }
  };

  /** Hide empty threads unless open; all agent sessions in one Chat sidebar. */
  const sidebarThreads = useMemo(() => {
    const visible = threadsVisibleInSidebar(threads, activeThreadId);
    return filterThreadsForChatSidebar(visible);
  }, [threads, activeThreadId]);

  const sidebarGroups = useMemo(
    () => buildSidebarGroups(sidebarThreads, dashboardTitles),
    [sidebarThreads, dashboardTitles]
  );

  const composerHasContent = useMemo(
    () => buildUserMessageContent(draft, pendingAttachments) !== "",
    [draft, pendingAttachments]
  );

  const canSend = useMemo(() => {
    if (!activeThreadId || loading || !(model || defaultModel) || !accessToken) return false;
    return composerHasContent;
  }, [activeThreadId, loading, model, defaultModel, accessToken, composerHasContent]);

  const canQueue = useMemo(() => {
    if (!activeThreadId || !loading || !(model || defaultModel) || !accessToken) return false;
    return composerHasContent;
  }, [activeThreadId, loading, model, defaultModel, accessToken, composerHasContent]);

  if (!hydrated || !userId) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center overflow-hidden text-sm text-surface-muted">
        {t("chat:loadingChats")}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden bg-surface">
      <aside className="flex h-full min-h-0 w-[280px] shrink-0 flex-col border-r border-surface-border bg-[#111]">
        <div className="shrink-0 border-b border-surface-border p-3">
          <button
            type="button"
            onClick={() => void startNewChat()}
            className="w-full rounded-lg border border-surface-border bg-white/5 px-3 py-2 text-left text-sm text-neutral-200 hover:bg-white/10"
          >
            {t("chat:newChat")}
          </button>
          <p className="mt-2 text-[11px] leading-snug text-surface-muted">
            Agent: WebSocket mit mehreren Runden. Chats sync zum Server.
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-surface-muted">
            {t("chat:sidebarTitle")}
          </p>
          <p className="mb-2 px-2 text-[10px] leading-snug text-surface-muted/80">
            {t("chat:sidebarHint")}{" "}
            <span className="text-amber-200/90">{t("chat:sharedBadge")}</span>
          </p>
          <div className="flex flex-col gap-3">
            {sidebarGroups.map((g) => (
              <section
                key={g.kind === "dashboard" ? `ws-${g.dashboardId}` : `src-${g.source}`}
                className="min-w-0"
              >
                <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wide text-surface-muted/90">
                  {g.label}
                </p>
                <ul className="flex flex-col gap-1">
                  {g.threads.map((thread) => (
                    <li key={thread.id}>
                      <div
                        className={`group flex items-start gap-1 rounded-md px-2 py-2 ${
                          thread.id === activeThreadId ? "bg-white/10" : "hover:bg-white/5"
                        }`}
                      >
                        <button
                          type="button"
                          className="min-w-0 flex-1 text-left text-sm text-neutral-200"
                          onClick={() => void selectThread(thread.id)}
                        >
                          <span className="flex flex-wrap items-start gap-1.5">
                            <span className="line-clamp-2 min-w-0 flex-1 text-left">{thread.title}</span>
                            <DashboardChatVisibilityBadge thread={thread} />
                          </span>
                          <span className="mt-0.5 block text-[10px] text-surface-muted">
                            {new Date(thread.updatedAt).toLocaleString(undefined, {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </button>
                        <div className="flex shrink-0 flex-col gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                          <button
                            type="button"
                            className="rounded px-1 text-[10px] text-surface-muted hover:text-white"
                            title={t("chat:rename")}
                            onClick={() => renameThread(thread.id)}
                          >
                            Ren
                          </button>
                          <button
                            type="button"
                            className="rounded px-1 text-[10px] text-surface-muted hover:text-white"
                            title={t("chat:copyLinkJson")}
                            onClick={() => void shareThread(thread)}
                          >
                            Share
                          </button>
                          <button
                            type="button"
                            className="rounded px-1 text-[10px] text-red-400/90 hover:text-red-300"
                            title={t("chat:delete")}
                            onClick={() => void deleteThread(thread.id)}
                          >
                            Del
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </div>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {!activeThreadId ? (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 px-6 py-12 text-center">
            <p className="max-w-md text-sm text-surface-muted">
              {t("chat:noConversationOpenLead")}{" "}
              <strong className="text-neutral-400">{t("chat:noConversationOpenBoldNone")}</strong>{" "}
              {t("chat:noConversationOpenMid")}{" "}
              <strong className="text-neutral-400">{t("chat:noConversationOpenBoldNew")}</strong>{" "}
              {t("chat:noConversationOpenEnd")}
            </p>
            <button
              type="button"
              onClick={() => void startNewChat()}
              className="rounded-lg border border-surface-border bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15"
            >
              {t("chat:newChat")}
            </button>
          </div>
        ) : (
          <>
        <div
          className={[
            "shrink-0 border-b border-surface-border px-4 sm:px-6",
            composerHeaderCollapsed ? "py-2" : "py-3",
          ].join(" ")}
        >
          <div
            className={[
              "flex min-w-0 flex-wrap items-center gap-2",
              composerHeaderCollapsed ? "" : "mb-2",
            ].join(" ")}
          >
            <p className="min-w-0 flex-1 truncate text-sm font-medium text-white">
              {activeThread?.title ?? t("chat:defaultThreadTitle")}
            </p>
            {activeThread ? <DashboardChatVisibilityBadge thread={activeThread} /> : null}
            <button
              type="button"
              className="shrink-0 rounded-lg border border-surface-border bg-black/30 px-2 py-1 text-[10px] font-medium text-neutral-300 hover:bg-white/10"
              aria-expanded={!composerHeaderCollapsed}
              aria-controls="chat-composer-header-panel"
              title={
                composerHeaderCollapsed
                  ? t("chat:expandComposerHeader")
                  : t("chat:collapseComposerHeader")
              }
              onClick={toggleComposerHeaderCollapsed}
            >
              {composerHeaderCollapsed ? "▼" : "▲"}
            </button>
          </div>
          {composerHeaderCollapsed ? (
            <p className="mt-1 truncate text-[10px] leading-snug text-surface-muted" title={composerHeaderSummary}>
              {composerHeaderSummary}
            </p>
          ) : null}
          {composerHeaderCollapsed && workspaceScopeHint && selectedWorkspaceId ? (
            <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-amber-600/40 bg-amber-950/30 px-3 py-2">
              <p className="min-w-0 flex-1 text-[11px] leading-snug text-amber-100/95">{workspaceScopeHint}</p>
              <button
                type="button"
                className="shrink-0 text-[11px] text-surface-muted hover:text-neutral-200"
                onClick={() => setWorkspaceScopeHint(null)}
              >
                {t("chat:dismiss")}
              </button>
            </div>
          ) : null}
          {!composerHeaderCollapsed ? (
          <div
            id="chat-composer-header-panel"
            className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_17.5rem] lg:items-stretch"
          >
            <div className="min-w-0 space-y-2">
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
                <div className="min-w-0 flex-1 sm:min-w-[10rem] sm:max-w-[20rem]">
                  <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                    {t("chat:assistantLabel")}
                  </label>
                  <p className="mt-0.5 rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-300">
                    {t("chat:generalAssistant")}
                  </p>
                  <p className="mt-1 text-[10px] leading-snug text-surface-muted">
                    {t("chat:generalAssistantHint")}
                  </p>
                </div>
                {workspaces.length > 0 ? (
                  <div className="min-w-0 flex-1 sm:min-w-[10rem] sm:max-w-[24rem]">
                    <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                      {t("chat:projectLabel")}
                    </label>
                    <div className="mt-0.5 flex flex-wrap gap-1.5">
                      <select
                        className="min-w-0 flex-1 rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                        value={selectedWorkspaceId ?? ""}
                        onChange={(e) => setComposerWorkspace(e.target.value || null)}
                      >
                        <option value="">{t("chat:noProject")}</option>
                        {workspaces.map((ws) => (
                          <option key={ws.id} value={ws.id}>
                            {ws.name}
                            {ws.access_role === "viewer" ? t("chat:projectViewerSuffix") : ""}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className={[
                          "shrink-0 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium",
                          projectPanelOpen
                            ? "border-sky-500/60 bg-sky-950/50 text-sky-100"
                            : "border-surface-border bg-black/30 text-neutral-300 hover:bg-white/10",
                        ].join(" ")}
                        disabled={!selectedWorkspaceId}
                        title={selectedWorkspaceId ? t("chat:showProjectTree") : t("chat:selectProjectFirst")}
                        onClick={() => {
                          const next = !projectPanelOpen;
                          setProjectPanelOpen(next);
                          setChatProjectPanelOpen(userId, next);
                        }}
                      >
                        {projectPanelOpen ? t("chat:hideTree") : t("chat:showTree")}
                      </button>
                      {selectedWorkspace &&
                      selectedWorkspace.access_role !== "viewer" &&
                      !isAgentlayerSelfWorkspace(selectedWorkspace) ? (
                        <button
                          type="button"
                          className="shrink-0 rounded-lg border border-red-900/40 bg-red-950/20 px-2.5 py-1.5 text-[11px] font-medium text-red-300/90 hover:bg-red-950/40"
                          title={t("chat:deleteProject")}
                          onClick={() => requestDeleteProject(selectedWorkspace)}
                        >
                          {t("chat:deleteProject")}
                        </button>
                      ) : null}
                    </div>
                    {selectedWorkspace ? (
                      <WorkspaceRetrievalBar
                        auth={auth}
                        workspace={selectedWorkspace}
                        canEdit={selectedWorkspace.access_role !== "viewer"}
                        onIndexActivity={handleIndexActivity}
                        onWorkspaceUpdated={(ws) => {
                          setWorkspaces((prev) => prev.map((w) => (w.id === ws.id ? ws : w)));
                        }}
                        className="mt-2 w-full"
                      />
                    ) : null}
                  </div>
                ) : null}
              </div>
              {workspaces.length === 0 ? (
                <div className="rounded-lg border border-surface-border bg-black/25 px-3 py-2">
                  <p className="text-xs leading-snug text-surface-muted">
                    {isAdminUser ? t("chat:noProjectsAdmin") : t("chat:noProjectsUser")}
                  </p>
                </div>
              ) : null}
              {workspaceScopeHint && selectedWorkspaceId ? (
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-600/40 bg-amber-950/30 px-3 py-2">
                  <p className="min-w-0 flex-1 text-[11px] leading-snug text-amber-100/95">{workspaceScopeHint}</p>
                  <button
                    type="button"
                    className="shrink-0 text-[11px] text-surface-muted hover:text-neutral-200"
                    onClick={() => setWorkspaceScopeHint(null)}
                  >
                    {t("chat:dismiss")}
                  </button>
                </div>
              ) : null}
              <p className="text-[10px] leading-snug text-surface-muted">{t("chat:titlesHint")}</p>
            </div>
            {mode === "agent" ? (
              <div className="flex min-h-0 w-full flex-col gap-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5">
                  <Link
                    to={
                      activeThreadId
                        ? `/tasks?conversation=${encodeURIComponent(activeThreadId)}${
                            selectedWorkspaceId
                              ? `&workspace=${encodeURIComponent(selectedWorkspaceId)}`
                              : ""
                          }`
                        : "/tasks"
                    }
                    className="text-[11px] text-sky-400/90 hover:text-sky-300 hover:underline"
                  >
                    {t("chat:tasksLink")}
                    {activeTaskId ? t("chat:tasksBoundHint") : ""}
                  </Link>
                  <span className="text-[10px] text-surface-muted">{t("chat:tasksBacklogHint")}</span>
                </div>
                <AgentActivityPanel
                  entries={activityEntries}
                  loading={activityLoading}
                  emptyHint={t("chat:activityEmptyHint")}
                  layout="header"
                  className="min-h-0 w-full"
                  showSubagentToggle={mode === "agent"}
                  showSubagents={showSubagentsInActivity}
                  onShowSubagentsChange={(on) => {
                    setShowSubagentsInActivity(on);
                    persistShowSubagentsPref(userId, on);
                  }}
                />
              </div>
            ) : (
              <div className="flex min-h-0 items-center rounded-lg border border-white/10 bg-black/30 px-2.5 py-2">
                <p className="text-[10px] leading-snug text-surface-muted">
                  {t("chat:switchToAgentModeHint")}
                </p>
              </div>
            )}
            <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-surface-border lg:pl-4">
              <SessionRuntimeBar
                runtime={sessionRuntime}
                usage={tokenUsage}
                contextMeta={chatContextMeta}
                className="w-full"
                mcpAddon={
                  selectedWorkspaceId &&
                  selectedWorkspace &&
                  selectedWorkspace.access_role !== "viewer" ? (
                    <button
                      type="button"
                      className="ml-0.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-white/15 px-1 text-[11px] font-medium text-sky-300/95 hover:bg-white/10"
                      title={t("workspace:editMcpServersWorkspaceOnlyTitle")}
                      onClick={() => setShowWorkspaceMcpModal(true)}
                    >
                      +
                    </button>
                  ) : null
                }
              />
              <div className="w-full">
                <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                  {t("chat:replyModeLabel")}
                </label>
                <select
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as ChatMode)}
                  title={t("chat:replyModeTitle")}
                >
                  <option value="agent">{t("chat:replyModeAgent")}</option>
                  <option value="chat">{t("chat:replyModeChat")}</option>
                </select>
                <p className="mt-1 text-[10px] leading-snug text-surface-muted">{t("chat:replyModeChatHint")}</p>
              </div>
              <div className="w-full">
                <label className="flex cursor-pointer items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                  <input
                    type="checkbox"
                    className="rounded border-surface-border bg-[#1a1a1a] text-sky-500"
                    checked={agentStreamLlmUi}
                    disabled={mode === "chat"}
                    onChange={(e) => {
                      const on = e.target.checked;
                      setAgentStreamLlm(on);
                      setAgentStreamLlmUi(on);
                    }}
                    title={
                      mode === "chat"
                        ? t("chat:agentLlmStreamTitleAgent")
                        : t("chat:agentLlmStreamTitle")
                    }
                  />
                  <span>{t("chat:agentLlmStreamLabel")}</span>
                </label>
                <p className="mt-1 pl-6 text-[10px] leading-snug text-surface-muted">
                  {t("chat:agentLlmStreamHint")}
                </p>
              </div>
              <div className="w-full">
                <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                  {t("chat:modelLabel")}
                </label>
                <select
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                  value={modelSelectValue || defaultSelectValue}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={!modelsCatalogReady || modelRows.length === 0}
                >
                  {!modelsCatalogReady ? (
                    <option value="">{t("chat:loadingModels")}</option>
                  ) : modelRows.length === 0 ? (
                    <option value="">
                      {formatEmptyChatModelCatalogHint(modelCatalogAgentlayer) ??
                        modelsCatalogHint ??
                            t("setup:noChatModels")}
                    </option>
                  ) : (
                    modelRows.map((row) => {
                      const catalogDown = isCatalogModelOptionDisabled(row, modelCatalogAgentlayer);
                      return (
                        <option
                          key={modelCatalogSelectValue(row)}
                          value={modelCatalogSelectValue(row)}
                          disabled={catalogDown}
                          title={catalogDown ? catalogModelOptionUnreachableTitle(row, modelCatalogAgentlayer) : undefined}
                        >
                          {modelOptionLabel(row, modelCatalogAgentlayer)}
                        </option>
                      );
                    })
                  )}
                </select>
                {modelsCatalogReady && modelsCatalogHint ? (
                  <p className="mt-1 text-xs text-amber-300/90">{modelsCatalogHint}</p>
                ) : null}
              </div>
            </div>
          </div>
          ) : null}
        </div>

        {dashboardChatId ? (
          <div className="shrink-0 border-b border-sky-900/40 bg-sky-950/25 px-6 py-2 text-sm text-sky-100/90">
            <span className="font-medium text-sky-200">{t("chat:dashboardContextLabel")}</span>
            {": "}
            {dashboardChatTitle ?? dashboardChatId}
            <span className="ml-2 text-xs text-sky-300/80">
              {t("chat:dashboardContextHint")}
            </span>
          </div>
        ) : null}

        {activeThread?.dashboardId && activeThread.shared ? (
          <div
            className="shrink-0 border-b border-amber-900/45 bg-amber-950/40 px-6 py-2.5 text-sm text-amber-50/95"
            role="status"
          >
            <span className="font-medium text-amber-200">{t("chat:sharedBannerTitle")}</span>
            {" — "}
            {t("chat:sharedBannerBody")}
          </div>
        ) : null}

        {activeThread?.dashboardId && activeThread.shared !== true ? (
          <div
            className="shrink-0 border-b border-emerald-900/35 bg-emerald-950/25 px-6 py-2 text-sm text-emerald-100/90"
            role="status"
          >
            <span className="font-medium text-emerald-200">{t("chat:personalBannerTitle")}</span>
            {" — "}
            {t("chat:personalBannerBody")}
          </div>
        ) : null}

        {error ? (
          <div className="shrink-0 border-b border-red-900/50 bg-red-950/40 px-6 py-2 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {userTurns.length > 0 ? (
            <TurnNavigatorHorizontal
              userTurns={userTurns}
              activeId={selectedTurnId}
              onSelect={handleSelectTurn}
              className="shrink-0 border-b border-surface-border px-4 py-2"
            />
          ) : null}
          <div className="flex min-h-0 flex-1 overflow-hidden">
            {projectPanelOpen && selectedWorkspaceId ? (
              <CodingWorkspacePanels
                auth={auth}
                workspaceId={selectedWorkspaceId}
                changesRefreshKey={projectTreeRefreshKey}
                variant="chat"
                readOnly={selectedWorkspace?.access_role === "viewer"}
              />
            ) : null}
            {userTurns.length > 0 ? (
              <aside className="hidden w-44 shrink-0 overflow-y-auto border-r border-surface-border px-2 py-4 lg:block">
                <TurnNavigator
                  userTurns={userTurns}
                  activeId={selectedTurnId}
                  onSelect={handleSelectTurn}
                />
              </aside>
            ) : null}
            <div
              ref={scrollContainerRef}
              className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-6 py-6"
            >
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-full border border-surface-border bg-white/5 text-lg font-semibold text-neutral-300">
                  AL
                </div>
                <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">
                  {t("chat:emptyHello", { name: displayName })}
                </h1>
                <p className="mt-2 max-w-md text-sm text-surface-muted">{t("chat:emptyIntro")}</p>
              </div>
            ) : (
              <ul className="mx-auto flex w-full max-w-3xl flex-col gap-3">
                {displayMessages.map((m, i) => {
                  if (m.role === "user") {
                    if (!chatMessageHasVisibleContent(m)) return null;
                    const isLastUser =
                      m.id != null && m.id === latestTurnId && lastUserMessageIndex(displayMessages) === i;
                    const showRetry =
                      Boolean(isLastUser) &&
                      !loading &&
                      turnHasAssistantAfter(displayMessages, m.id!);
                    return (
                      <li
                        key={m.id ?? `${i}-user-${m.content.slice(0, 24)}`}
                        id={m.id ? `msg-${m.id}` : undefined}
                        className="flex w-full scroll-mt-4 justify-start"
                      >
                        <UserMessageBubble
                          message={m}
                          timeLabel={formatMessageTime(m.createdAt)}
                          showRetry={showRetry}
                          onCopy={() => void copyUserMessage(m.content)}
                          onRetry={() => retryUserTurn(m.id!)}
                        />
                      </li>
                    );
                  }
                  if (m.role !== "assistant") return null;

                  const turnId = userTurnIdBeforeAssistant(displayMessages, i);
                  const timelineEntries = timelineForTurn(activeThread, turnId);
                  const isLast = i === displayMessages.length - 1;
                  const inFlight =
                    loading && mode === "agent" && isLast && selectedTurnId === latestTurnId;
                  const segments = buildInterleavedTurnSegments(m.content, timelineEntries);
                  const hasStreamBody = segments.some(
                    (s) =>
                      (s.type === "text" && s.text.trim().length > 0) ||
                      s.type === "card" ||
                      s.type === "secret_prompt"
                  );
                  if (!hasStreamBody && !inFlight) return null;

                  return (
                    <AssistantTurnBlock
                      key={m.id ?? `${i}-assistant-${m.content.slice(0, 24)}`}
                      content={m.content}
                      timelineEntries={timelineEntries}
                      running={inFlight && !hasStreamBody}
                      createdAt={m.createdAt}
                      auth={auth}
                      selectedByProposalId={proposalSelectionMap}
                      onSelectProposalOption={handleSelectProposalOption}
                      onSecretSaved={handleSecretSaved}
                    />
                  );
                })}
                {loading &&
                mode === "agent" &&
                latestTurnId &&
                displayMessages.length > 0 &&
                displayMessages[displayMessages.length - 1]?.role === "user" ? (
                  <AssistantTurnBlock
                    key={`assistant-inflight-${latestTurnId}`}
                    content=""
                    timelineEntries={timelineForTurn(activeThread, latestTurnId)}
                    running
                    auth={auth}
                    selectedByProposalId={proposalSelectionMap}
                    onSelectProposalOption={handleSelectProposalOption}
                    onSecretSaved={handleSecretSaved}
                  />
                ) : null}
                {loading &&
                mode === "chat" &&
                !(
                  displayMessages.length > 0 &&
                  displayMessages[displayMessages.length - 1]?.role === "assistant" &&
                  chatMessageHasVisibleContent(displayMessages[displayMessages.length - 1]!)
                ) ? (
                  <li className="flex w-full justify-end">
                    <div className="max-w-[min(100%,42rem)] rounded-2xl border border-sky-900/50 bg-sky-950/25 px-4 py-3 text-sm text-sky-100/90 shadow-sm">
                      <span className="mb-1 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-sky-300/80">
                        <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-sky-400" />
                        {t("chat:roleAssistant")}
                      </span>
                      <p className="text-neutral-300">{t("chat:generatingReply")}</p>
                    </div>
                  </li>
                ) : null}
              </ul>
            )}
            <div ref={messagesEndRef} className="h-px w-full shrink-0" aria-hidden />
            </div>
          </div>
        </div>

        <div className="shrink-0 border-t border-surface-border bg-[#0c0c0c] px-6 py-4">
          <div className="relative mx-auto max-w-3xl">
            {showScrollFab ? (
              <button
                type="button"
                onClick={() => scrollToBottom("smooth")}
                className="absolute -top-12 right-0 z-10 rounded-full border border-surface-border bg-[#1a1a1a] px-3 py-1.5 text-xs text-neutral-200 shadow-lg hover:bg-[#252525]"
                aria-label={t("chat:scrollToBottomAria")}
              >
                {t("chat:newMessages")}
              </button>
            ) : null}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              accept="image/*,.txt,.md,.json,.csv,.log,.yaml,.yml,.zip"
              onChange={(e) => {
                const files = e.target.files;
                e.target.value = "";
                void addPickedFiles(files);
              }}
            />
            <div
              role="group"
              aria-label={t("chat:composerAria")}
              className={`relative rounded-2xl border bg-[#141414] p-3 shadow-xl transition-colors ${
                composerDragActive
                  ? "border-sky-500/70 ring-2 ring-sky-500/25"
                  : "border-surface-border"
              }`}
              onDragEnter={(e) => {
                e.preventDefault();
                if (!Array.from(e.dataTransfer.types).includes("Files")) return;
                setComposerDragActive(true);
              }}
              onDragLeave={(e) => {
                const next = e.relatedTarget as Node | null;
                if (next && e.currentTarget.contains(next)) return;
                setComposerDragActive(false);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
              }}
              onDrop={(e) => {
                e.preventDefault();
                setComposerDragActive(false);
                void addPickedFiles(e.dataTransfer.files);
              }}
            >
              {composerDragActive ? (
                <div
                  className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-sky-950/50 backdrop-blur-[1px]"
                  aria-hidden
                >
                  <p className="rounded-lg border border-sky-500/40 bg-black/50 px-4 py-2 text-sm font-medium text-sky-100">
                    {t("chat:dropFilesToAttach")}
                  </p>
                </div>
              ) : null}
              {activeComposerQueue.length > 0 ? (
                <ul className="mb-2 space-y-1 rounded-lg border border-violet-500/25 bg-violet-950/20 px-2 py-1.5">
                  <li className="text-[9px] font-medium uppercase tracking-wide text-violet-200/80">
                    {t("chat:composerQueueTitle", { count: activeComposerQueue.length })}
                  </li>
                  {activeComposerQueue.map((item, idx) => (
                    <li
                      key={item.id}
                      className="flex items-start gap-2 text-[11px] text-neutral-300"
                    >
                      <span className="shrink-0 tabular-nums text-violet-300/70">{idx + 1}.</span>
                      <span className="min-w-0 flex-1 truncate" title={queueItemPreview(item)}>
                        {queueItemPreview(item)}
                      </span>
                      <button
                        type="button"
                        className="shrink-0 rounded px-1 text-surface-muted hover:text-white"
                        aria-label={t("chat:composerQueueRemove")}
                        onClick={() => removeFromComposerQueue(item.id)}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {pendingAttachments.length > 0 ? (
                <ul className="mb-2 flex flex-wrap gap-2">
                  {pendingAttachments.map((a, idx) => (
                    <li
                      key={`${a.name}-${idx}`}
                      className="flex max-w-full items-center gap-1 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-xs text-neutral-300"
                    >
                      <span className="truncate" title={a.kind === "unsupported" ? a.hint : a.name}>
                        {a.name}
                        {a.kind === "unsupported" ? t("chat:attachmentNotSent") : ""}
                      </span>
                      <button
                        type="button"
                        className="shrink-0 rounded px-1 text-surface-muted hover:text-white"
                        aria-label={t("chat:removeAttachment")}
                        onClick={() => setPendingAttachments((prev) => prev.filter((_, i) => i !== idx))}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <textarea
                className="min-h-[52px] w-full resize-none bg-transparent text-sm text-neutral-100 placeholder:text-neutral-500 focus:outline-none"
                placeholder={t("chat:composerPlaceholder")}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={2}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (canSend) onSend();
                    else if (canQueue) onQueue();
                  }
                }}
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <button
                  type="button"
                  className="rounded-lg border border-white/10 bg-black/20 p-2 text-surface-muted hover:bg-white/5 hover:text-neutral-200 disabled:opacity-40"
                  title={t("chat:attachTitle")}
                  aria-label={t("chat:attachFiles")}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                </button>
                {loading ? (
                  <div className="flex items-center gap-2">
                    {canQueue ? (
                      <button
                        type="button"
                        className="rounded-lg border border-violet-500/50 bg-violet-950/40 px-4 py-2 text-sm font-medium text-violet-100 hover:bg-violet-900/50"
                        onClick={() => onQueue()}
                      >
                        {t("chat:composerQueueAdd")}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="rounded-lg border border-amber-500/60 bg-amber-950/50 px-4 py-2 text-sm font-medium text-amber-100 hover:bg-amber-900/40"
                      onClick={() => onCancelInFlight()}
                    >
                      {t("admin:cancel")}
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={!canSend}
                    className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-40"
                    onClick={() => onSend()}
                  >
                    {t("dashboard:send")}
                  </button>
                )}
              </div>
            </div>

            {messages.length === 0 ? (
              <div className="mt-6">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-surface-muted">
                  Suggested
                </p>
                <ul className="flex flex-col gap-2">
                  {suggested.map((s) => (
                    <li key={s}>
                      <button
                        type="button"
                        className="w-full rounded-lg border border-surface-border bg-[#141414] px-4 py-3 text-left text-sm text-neutral-300 hover:bg-white/5"
                        onClick={() => setDraft(s)}
                      >
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
          </>
        )}
      </main>
      {showWorkspaceMcpModal && selectedWorkspaceId && selectedWorkspace ? (
        <WorkspaceMcpModal
          open={showWorkspaceMcpModal}
          onClose={() => setShowWorkspaceMcpModal(false)}
          auth={auth}
          workspaceId={selectedWorkspaceId}
          workspaceName={selectedWorkspace.name}
          workspacePath={selectedWorkspace.path}
          initialServers={selectedWorkspace.mcp_stdio_servers}
          onSaved={async () => {
            try {
              const r = await apiFetch("/v1/workspaces", auth);
              if (r.ok) {
                const j = (await r.json()) as { workspaces?: WorkspaceApiRecord[] };
                setWorkspaces(j.workspaces ?? []);
              }
              const wsParam = selectedWorkspaceId ? selectedWorkspaceId : null;
              setSessionRuntime(await fetchSessionRuntime(auth, wsParam));
            } catch {
              /* ignore */
            }
          }}
        />
      ) : null}
      <ConfirmModal
        open={deleteProjectTarget != null}
        title={t("chat:deleteProjectTitle")}
        description={
          deleteProjectTarget
            ? t("chat:deleteProjectDescription", { name: deleteProjectTarget.name })
            : ""
        }
        confirmLabel={t("chat:deleteProjectConfirm")}
        cancelLabel={t("admin:cancel")}
        variant="danger"
        busy={deletingProject}
        onConfirm={() => void confirmDeleteProject()}
        onCancel={() => {
          if (!deletingProject) setDeleteProjectTarget(null);
        }}
      />
    </div>
  );
}
