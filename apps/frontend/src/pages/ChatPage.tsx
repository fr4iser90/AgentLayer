import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, addUsageTotals, emptyTokenUsage, fetchAgents, fetchSessionRuntime, type AgentDefinition, type SessionRuntimePayload, type TokenUsageTotals, type WorkspaceApiRecord } from "../lib/api";
import {
  applyModelCatalogSelection,
  defaultModelCatalogSelectValue,
  fetchModelCatalog,
  findCatalogRowByModelId,
  formatEmptyChatModelCatalogHint,
  formatModelCatalogHint,
  catalogModelOptionUnreachableTitle,
  isCatalogModelOptionDisabled,
  modelCatalogSelectValue,
  modelCatalogSelectValueForThread,
  modelOptionLabel,
  normalizeCatalogRoutingToken,
  parseModelCatalogSelection,
  resolveComposerModelRouting,
  resolveModelCatalogRouting,
  type ModelCatalogAgentlayer,
  type ModelRow,
} from "../lib/modelCatalog";
import {
  NEW_CHAT_TITLE,
  type AgentTimelineEntry,
  type ChatMode,
  type ChatThread,
  type UiMessage,
  exportThreadJson,
  titleFromFirstMessage,
} from "../features/chat/chatThreadStorage";

/** Dashboard-linked thread: show whether other members see messages (shared) or only you (personal). */
function DashboardChatVisibilityBadge({ thread }: { thread: Pick<ChatThread, "dashboardId" | "shared"> }) {
  if (!thread.dashboardId) return null;
  const shared = thread.shared === true;
  if (shared) {
    return (
      <span
        className="inline-flex shrink-0 items-center rounded-full border border-amber-400/40 bg-amber-950/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-100/95"
        title="Shared dashboard chat — other members can read messages in this thread."
      >
        Shared
      </span>
    );
  }
  return (
    <span
      className="inline-flex shrink-0 items-center rounded-full border border-emerald-500/35 bg-emerald-950/45 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-100/90"
      title="Personal dashboard chat — only you see this thread."
    >
      Personal
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
  parseContentParts,
  toApiContent,
  type PendingAttachment,
} from "../features/chat/messageFormat";
import { getDisabledToolNames } from "../features/settings/toolPrefs";
import { getAgentStreamLlm, setAgentStreamLlm } from "../features/settings/agentStreamPrefs";
import { buildSidebarGroups } from "../features/chat/groupThreadsForSidebar";
import { SessionRuntimeBar } from "../features/chat/SessionRuntimeBar";
import { WorkspaceMcpModal } from "../features/workspace/WorkspaceMcpModal";
import { streamOpenAiChatChunks } from "../features/chat/openaiSseStream";

const SUGGESTED = [
  "Show me a code snippet of a website's sticky header",
  "Explain options trading if I'm familiar with buying and selling stocks",
  "Help me study vocabulary for a college entrance exam",
];

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
  return [...baseline, { role: "assistant", content: accumulated }];
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

function MessageBody({ content }: { content: string }) {
  const { plain, parts } = parseContentParts(content);
  if (parts) {
    return (
      <div className="space-y-2">
        {parts.map((p, i) => {
          if (p.type === "text" && p.text) {
            return (
              <div key={i} className="whitespace-pre-wrap">
                {p.text}
              </div>
            );
          }
          if (p.type === "image_url" && p.image_url?.url) {
            return (
              <img
                key={i}
                src={p.image_url.url}
                alt=""
                className="max-h-64 max-w-full rounded-md border border-white/10 object-contain"
              />
            );
          }
          return null;
        })}
      </div>
    );
  }
  return <div className="whitespace-pre-wrap">{plain}</div>;
}

export function ChatPage() {
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
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("general");
  const [sessionRuntime, setSessionRuntime] = useState<SessionRuntimePayload | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsageTotals>(() => emptyTokenUsage());

  const isAdminUser = (user?.role ?? "").toLowerCase() === "admin";
  const visibleAgents = useMemo(
    () =>
      agents.filter(
        (a) => (a.min_role ?? "user").toLowerCase() !== "admin" || isAdminUser
      ),
    [agents, isAdminUser]
  );

  const [workspaces, setWorkspaces] = useState<WorkspaceApiRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [showWorkspaceMcpModal, setShowWorkspaceMcpModal] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const agentHandlerRef = useRef<(ev: MessageEvent) => void>(() => {});
  /** User cancelled before the chat frame was sent (e.g. while WebSocket connects). */
  const cancelAgentTurnRef = useRef(false);
  /** In-flight HTTP chat completion (stream or JSON). */
  const chatAbortControllerRef = useRef<AbortController | null>(null);
  const activeThreadIdRef = useRef<string | null>(null);
  const lastModelSelectionRef = useRef("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const toolStartTimesRef = useRef<Map<string, number>>(new Map());
  const agentTurnBaselineRef = useRef<UiMessage[] | null>(null);
  const streamDeltaAccRef = useRef("");
  const agentStreamEnabledThisTurnRef = useRef(false);
  const [agentStreamLlmUi, setAgentStreamLlmUi] = useState(() => getAgentStreamLlm());
  activeThreadIdRef.current = activeThreadId;

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
    () => threads.find((t) => t.id === activeThreadId) ?? null,
    [threads, activeThreadId]
  );

  const threadComposerAgentId = activeThread?.agentId;
  const threadComposerWorkspaceId = activeThread?.workspaceId;

  useEffect(() => {
    if (!activeThreadId || !visibleAgents.length) return;
    const aid =
      typeof threadComposerAgentId === "string" && threadComposerAgentId.trim()
        ? threadComposerAgentId.trim()
        : null;
    if (aid && visibleAgents.some((a) => a.id === aid)) {
      setSelectedAgentId(aid);
    } else {
      const g = visibleAgents.find((a) => a.id === "general");
      if (g) setSelectedAgentId(g.id);
      else if (visibleAgents[0]) setSelectedAgentId(visibleAgents[0].id);
    }
    const wid =
      typeof threadComposerWorkspaceId === "string" && threadComposerWorkspaceId.trim()
        ? threadComposerWorkspaceId.trim()
        : null;
    setSelectedWorkspaceId(wid || null);
  }, [
    activeThreadId,
    visibleAgents,
    threadComposerAgentId,
    threadComposerWorkspaceId,
  ]);

  const messages = activeThread?.messages ?? [];
  const mode: ChatMode = activeThread?.mode ?? "agent";
  const model = activeThread?.model ?? "";
  const modelProvider = activeThread?.modelProvider;
  const agentLog: AgentTimelineEntry[] = activeThread?.agentLog ?? [];

  const defaultSelectValue = useMemo(
    () => defaultModelCatalogSelectValue(modelRows),
    [modelRows]
  );
  const defaultModel = useMemo(() => {
    const p = parseModelCatalogSelection(defaultSelectValue);
    return p.modelId || modelRows[0]?.id || "";
  }, [defaultSelectValue, modelRows]);
  const modelSelectValue = useMemo(() => {
    const fromThread = modelCatalogSelectValueForThread(model, modelProvider);
    if (fromThread.includes(":")) return fromThread;
    const row = findCatalogRowByModelId(modelRows, model, modelProvider);
    if (row) return modelCatalogSelectValue(row);
    if (model.trim()) return fromThread;
    return defaultSelectValue;
  }, [model, modelProvider, defaultSelectValue, modelRows]);

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
          setModelsCatalogHint("Could not load model catalog.");
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
      try {
        const ags = await fetchAgents(auth);
        if (cancelled) return;
        setAgents(ags);
        if (ags.length === 0) return;
        setSelectedAgentId((prev) => {
          if (ags.some((a) => a.id === prev)) return prev;
          const general = ags.find((a) => a.id === "general");
          return general ? general.id : ags[0].id;
        });
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const agent = visibleAgents.find((a) => a.id === selectedAgentId);
      const wsParam =
        agent?.requires_workspace && selectedWorkspaceId ? selectedWorkspaceId : null;
      const r = await fetchSessionRuntime(auth, wsParam);
      if (!cancelled) setSessionRuntime(r);
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, selectedAgentId, selectedWorkspaceId, visibleAgents]);

  useEffect(() => {
    if (!visibleAgents.length) return;
    if (!visibleAgents.some((a) => a.id === selectedAgentId)) {
      const g = visibleAgents.find((a) => a.id === "general");
      setSelectedAgentId(g ? g.id : visibleAgents[0].id);
    }
  }, [visibleAgents, selectedAgentId]);

  useEffect(() => {
    if (!selectedAgentId || !accessToken) {
      setWorkspaces([]);
      setSelectedWorkspaceId(null);
      return;
    }
    const agent = visibleAgents.find((a) => a.id === selectedAgentId);
    if (!agent?.requires_workspace) {
      setWorkspaces([]);
      setSelectedWorkspaceId(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const r = await apiFetch("/v1/workspaces", auth);
        if (!r.ok || cancelled) return;
        const j = (await r.json()) as { workspaces?: WorkspaceApiRecord[] };
        if (cancelled) return;
        setWorkspaces(j.workspaces ?? []);
        setSelectedWorkspaceId((prev) => {
          const list = j.workspaces ?? [];
          if (prev && list.some((w: WorkspaceApiRecord) => w.id === prev)) return prev;
          return list[0]?.id ?? null;
        });
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedAgentId, accessToken, auth, visibleAgents]);

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
          setError(e instanceof Error ? e.message : "Could not load chats (server sync)");
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, loading, activeThreadId]);

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
    const hint = lastModelSelectionRef.current || modelSelectValue || defaultSelectValue;
    const routed = resolveModelCatalogRouting(modelRows, th.model, th.modelProvider, hint);
    if (!routed) return;
    if (th.model === routed.model && th.modelProvider === routed.provider) return;
    lastModelSelectionRef.current = modelCatalogSelectValueForThread(
      routed.model,
      routed.provider
    );
    patchThread(activeThreadId, { model: routed.model, modelProvider: routed.provider });
  }, [activeThreadId, defaultSelectValue, modelsCatalogReady, modelRows, modelSelectValue, threads, patchThread]);

  const addPickedFiles = useCallback(async (files: FileList | File[] | null) => {
    if (!files?.length) return;
    try {
      const next = await filesToAttachments(files);
      setPendingAttachments((prev) => [...prev, ...next]);
    } catch {
      setError("Could not read file");
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

  const setComposerAgent = useCallback(
    (agentId: string) => {
      if (!activeThreadId) return;
      setSelectedAgentId(agentId);
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === activeThreadId ? { ...t, agentId, updatedAt: Date.now() } : t
        );
        const th = next.find((x) => x.id === activeThreadId);
        if (th) void putConversation(auth, th).catch(() => {});
        return next;
      });
    },
    [activeThreadId, auth]
  );

  const setComposerWorkspace = useCallback(
    (wsId: string | null) => {
      if (!activeThreadId) return;
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
    [activeThreadId, auth]
  );

  const appendAgentLine = useCallback((kind: string, text: string) => {
    const tid = activeThreadIdRef.current;
    if (!tid) return;
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== tid) return t;
        const next: AgentTimelineEntry[] = [
          ...(t.agentLog ?? []),
          { id: `${Date.now()}-${(t.agentLog ?? []).length}`, kind, text },
        ];
        return { ...t, agentLog: next, updatedAt: Date.now() };
      })
    );
  }, []);

  const runChatHttp = useCallback(async () => {
    if (!accessToken || !activeThreadId) return;
    const tid = activeThreadId;
    const t = threads.find((x) => x.id === tid);
    const routed = resolveComposerModelRouting(
      modelRows,
      lastModelSelectionRef.current || modelSelectValue,
      (t?.model || defaultModel).trim(),
      t?.modelProvider
    );
    if (!t || !routed) {
      setError(
        "Could not resolve model provider. Open the model list and pick an entry (provider shown in parentheses)."
      );
      return;
    }

    const userContent = buildUserMessageContent(draft, pendingAttachments);
    if (!userContent) return;

    setError(null);
    setLoading(true);
    setTokenUsage(emptyTokenUsage());
    const firstUser = t.messages.length === 0;
    const nextMessages: UiMessage[] = [...t.messages, { role: "user", content: userContent }];
    const nextTitle = firstUser ? titleFromFirstMessage(userContent) : t.title;
    patchThread(tid, {
      messages: nextMessages,
      title: nextTitle,
      model: routed.model,
      modelProvider: routed.provider,
    });
    setDraft("");
    setPendingAttachments([]);

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
                return {
                  ...th,
                  messages: [...nextMessages, { role: "assistant", content: acc }],
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
        const reply = acc.trim() || "(empty)";
        setThreads((prev) => {
          const next = prev.map((th) => {
            if (th.id !== tid) return th;
            const updated: ChatThread = {
              ...th,
              messages: [...nextMessages, { role: "assistant", content: reply }],
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
      if (data && typeof data === "object" && "usage" in data) {
        setTokenUsage((prev) => addUsageTotals(prev, (data as { usage?: unknown }).usage));
      }
      const content = assistantFromCompletion(data);
      setThreads((prev) => {
        const next = prev.map((th) => {
          if (th.id !== tid) return th;
          const updated: ChatThread = {
            ...th,
            messages: [...th.messages, { role: "assistant", content: content || "(empty)" }],
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
    threads,
  ]);

  const ensureAgentWs = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const tok = accessToken;
      if (!tok) {
        reject(new Error("Not signed in"));
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
      ws.onerror = () => reject(new Error("WebSocket connection failed"));
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
      };
    });
  }, [accessToken]);

  const runAgentWs = useCallback(async () => {
    if (!accessToken || !activeThreadId) return;
    const tid = activeThreadId;
    const t = threads.find((x) => x.id === tid);
    const routed = resolveComposerModelRouting(
      modelRows,
      lastModelSelectionRef.current || modelSelectValue,
      (t?.model || defaultModel).trim(),
      t?.modelProvider
    );
    if (!t || !routed) {
      setError(
        "Could not resolve model provider. Open the model list and pick an entry (provider shown in parentheses)."
      );
      return;
    }

    const userContent = buildUserMessageContent(draft, pendingAttachments);
    if (!userContent) return;

    setError(null);
    setLoading(true);
    setTokenUsage(emptyTokenUsage());
    const firstUser = t.messages.length === 0;
    const nextMessages: UiMessage[] = [...t.messages, { role: "user", content: userContent }];
    const nextTitle = firstUser ? titleFromFirstMessage(userContent) : t.title;
    patchThread(tid, {
      messages: nextMessages,
      agentLog: [],
      title: nextTitle,
      model: routed.model,
      modelProvider: routed.provider,
    });
    agentTurnBaselineRef.current = nextMessages;
    streamDeltaAccRef.current = "";
    agentStreamEnabledThisTurnRef.current = getAgentStreamLlm();
    setDraft("");
    setPendingAttachments([]);

    cancelAgentTurnRef.current = false;

    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      setLoading(false);
      const id = activeThreadIdRef.current;
      if (id) {
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

    agentHandlerRef.current = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        const typ = msg.type;
        if (typ === "pong") return;
        if (typ === "error") {
          setError(typeof msg.detail === "string" ? msg.detail : "Agent error");
          finish();
          return;
        }
        if (typ === "chat.completion") {
          if (msg.error) {
            setError(typeof msg.detail === "string" ? msg.detail : "Cancelled or failed");
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
            setThreads((prev) => {
              const next = prev.map((th) => {
                if (th.id !== id) return th;
                const prevMsgs = th.messages;
                const last = prevMsgs[prevMsgs.length - 1];
                const replaceLastAssistant =
                  agentStreamEnabledThisTurnRef.current &&
                  last?.role === "assistant";
                const messages: UiMessage[] = replaceLastAssistant
                  ? [...prevMsgs.slice(0, -1), { role: "assistant", content }]
                  : [...prevMsgs, { role: "assistant", content }];
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
          }
          finish();
          return;
        }
        if (typ === "agent.session") {
          const em = msg.effective_model != null ? String(msg.effective_model) : "";
          const mr = msg.model_resolution != null ? String(msg.model_resolution) : "";
          appendAgentLine("session", [em && `model: ${em}`, mr && `(${mr})`].filter(Boolean).join(" "));
          if (msg.agent_auto_routed === true && msg.effective_agent_id != null) {
            const aid = String(msg.effective_agent_id).trim();
            if (aid) {
              setSelectedAgentId(aid);
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
          if (msg.workspace_auto_created === true && msg.workspace_id != null) {
            const wid = String(msg.workspace_id).trim();
            if (wid) {
              setSelectedWorkspaceId(wid);
              const tid = activeThreadIdRef.current;
              if (tid) {
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
        if (typ === "agent.tool_start") {
          const toolName = String(msg.name ?? "tool");
          toolStartTimesRef.current.set(toolName, Date.now());
          appendAgentLine("tool", `→ ${toolName}`);
          return;
        }
        if (typ === "agent.tool_done") {
          const n = msg.name != null ? String(msg.name) : "tool";
          const ch = msg.result_chars != null ? String(msg.result_chars) : "";
          const durationMs = msg.duration_ms != null ? Number(msg.duration_ms) : null;
          
          let durationText = "";
          if (durationMs != null && durationMs >= 0) {
            if (durationMs < 1000) {
              durationText = `${durationMs} ms`;
            } else if (durationMs < 60000) {
              durationText = `${(durationMs / 1000).toFixed(1)} s`;
            } else {
              durationText = `${(durationMs / 60000).toFixed(1)} min`;
            }
          } else {
            // Fallback wenn Backend noch keine duration_ms mitschickt
            const startTime = toolStartTimesRef.current.get(n);
            if (startTime != null) {
              const ms = Date.now() - startTime;
              toolStartTimesRef.current.delete(n);
              
              if (ms < 1000) {
                durationText = `${ms} ms`;
              } else if (ms < 60000) {
                durationText = `${(ms / 1000).toFixed(1)} s`;
              } else {
                durationText = `${(ms / 60000).toFixed(1)} min`;
              }
            }
          }

          const parts: string[] = [];
          if (ch) parts.push(`${ch} chars`);
          if (durationText) parts.push(durationText);
          
          appendAgentLine("tool", `← ${n}${parts.length ? ` (${parts.join(", ")})` : ""}`);
          return;
        }
        if (typ === "agent.step_wait") {
          appendAgentLine("wait", "Paused (step mode)");
          return;
        }
        if (typ === "agent.done" || typ === "agent.aborted" || typ === "agent.cancelled") {
          appendAgentLine(String(typ), String(msg.detail ?? ""));
          return;
        }
        appendAgentLine(String(typ ?? "event"), JSON.stringify(msg).slice(0, 300));
      } catch {
        setError("Invalid WebSocket message");
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
            agent_id: selectedAgentId,
            ...(selectedWorkspaceId ? { workspace_id: selectedWorkspaceId } : {}),
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
    selectedAgentId,
    selectedWorkspaceId,
    threads,
    visibleAgents,
  ]);

  const onSend = () => {
    void (mode === "chat" ? runChatHttp() : runAgentWs());
  };

  const onCancelInFlight = useCallback(() => {
    if (mode === "chat") {
      chatAbortControllerRef.current?.abort();
      setLoading(false);
      return;
    }
    cancelAgentTurnRef.current = true;
    setLoading(false);
    const w = wsRef.current;
    if (w?.readyState === WebSocket.OPEN) {
      try {
        w.send(JSON.stringify({ type: "cancel" }));
      } catch {
        /* ignore */
      }
    }
  }, [mode]);

  const startNewChat = async () => {
    try {
      const defaultProv = parseModelCatalogSelection(defaultSelectValue).provider;
      const t = await createConversation(auth, {
        title: NEW_CHAT_TITLE,
        mode: "agent",
        model: defaultModel,
        messages: [],
        agent_log: [],
        model_catalog_owned_by: defaultProv ?? null,
      });
      setThreads((prev) => [t, ...prev]);
      setActiveThreadId(t.id);
      setSearchParams({ c: t.id });
      setDraft("");
      setError(null);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const deleteThread = async (id: string) => {
    if (!confirm("Delete this chat?")) return;
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
    const t = threads.find((x) => x.id === id);
    if (!t) return;
    const next = window.prompt("Chat title", t.title);
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed) return;
    patchThread(id, { title: trimmed });
    void putConversation(auth, { ...t, title: trimmed }).catch(() => {});
  };

  const shareThread = async (t: ChatThread) => {
    const url = `${window.location.origin}/app/chat?c=${encodeURIComponent(t.id)}`;
    try {
      await navigator.clipboard.writeText(url + "\n\n" + exportThreadJson(t));
    } catch {
      setError("Could not copy");
    }
  };

  /** Hide empty threads unless they are the one currently open (avoids fake sidebar clutter). */
  const sidebarThreads = useMemo(
    () =>
      threads.filter((t) => threadMessageCount(t) > 0 || t.id === activeThreadId),
    [threads, activeThreadId]
  );

  const sidebarGroups = useMemo(
    () => buildSidebarGroups(sidebarThreads, dashboardTitles),
    [sidebarThreads, dashboardTitles]
  );

  const canSend = useMemo(() => {
    if (!activeThreadId || loading || !(model || defaultModel) || !accessToken) return false;
    return buildUserMessageContent(draft, pendingAttachments) !== "";
  }, [activeThreadId, loading, model, defaultModel, accessToken, draft, pendingAttachments]);

  if (!hydrated || !userId) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center overflow-hidden text-sm text-surface-muted">
        Loading chats…
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
            + New chat
          </button>
          <p className="mt-2 text-[11px] leading-snug text-surface-muted">
            Agent: WebSocket mit mehreren Runden. Chats sync zum Server.
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-surface-muted">
            Your chats
          </p>
          <p className="mb-2 px-2 text-[10px] leading-snug text-surface-muted/80">
            Empty threads stay hidden until you open them or send a message. Dashboard rows marked{" "}
            <span className="text-amber-200/90">Shared</span> are older team chats (or API); new assistants are private
            by default.
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
                  {g.threads.map((t) => (
                    <li key={t.id}>
                      <div
                        className={`group flex items-start gap-1 rounded-md px-2 py-2 ${
                          t.id === activeThreadId ? "bg-white/10" : "hover:bg-white/5"
                        }`}
                      >
                        <button
                          type="button"
                          className="min-w-0 flex-1 text-left text-sm text-neutral-200"
                          onClick={() => void selectThread(t.id)}
                        >
                          <span className="flex flex-wrap items-start gap-1.5">
                            <span className="line-clamp-2 min-w-0 flex-1 text-left">{t.title}</span>
                            <DashboardChatVisibilityBadge thread={t} />
                          </span>
                          <span className="mt-0.5 block text-[10px] text-surface-muted">
                            {new Date(t.updatedAt).toLocaleString(undefined, {
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
                            title="Rename"
                            onClick={() => renameThread(t.id)}
                          >
                            Ren
                          </button>
                          <button
                            type="button"
                            className="rounded px-1 text-[10px] text-surface-muted hover:text-white"
                            title="Copy link + JSON"
                            onClick={() => void shareThread(t)}
                          >
                            Share
                          </button>
                          <button
                            type="button"
                            className="rounded px-1 text-[10px] text-red-400/90 hover:text-red-300"
                            title="Delete"
                            onClick={() => void deleteThread(t.id)}
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
              No conversation open. Threads with <strong className="text-neutral-400">no messages</strong> stay out of
              the sidebar until you send something. Use <strong className="text-neutral-400">+ New chat</strong> to
              start.
            </p>
            <button
              type="button"
              onClick={() => void startNewChat()}
              className="rounded-lg border border-surface-border bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15"
            >
              + New chat
            </button>
          </div>
        ) : (
          <>
        <div className="shrink-0 border-b border-surface-border px-4 py-3 sm:px-6">
          <div className="mb-2 flex min-w-0 flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-white">{activeThread?.title ?? "Chat"}</p>
            {activeThread ? <DashboardChatVisibilityBadge thread={activeThread} /> : null}
          </div>
          <div className="grid gap-3 lg:grid-cols-[1fr,17.5rem] lg:items-start">
            <div className="min-w-0 space-y-2">
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
                <div className="min-w-0 flex-1 sm:min-w-[10rem] sm:max-w-[20rem]">
                  <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                    Agent
                  </label>
                  <select
                    className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                    value={selectedAgentId}
                    onChange={(e) => setComposerAgent(e.target.value)}
                    disabled={!visibleAgents.length || mode === "chat"}
                    title={
                      mode === "chat"
                        ? "Chat mode uses plain completion without tools; switch to Agent mode to use this agent."
                        : undefined
                    }
                  >
                    {!visibleAgents.length ? (
                      <option>Loading agents…</option>
                    ) : (
                      visibleAgents.map((ag) => (
                        <option key={ag.id} value={ag.id}>
                          {ag.icon} {ag.name}
                        </option>
                      ))
                    )}
                  </select>
                </div>
                {(() => {
                  const agent = visibleAgents.find((a) => a.id === selectedAgentId);
                  if (!agent?.requires_workspace) return null;
                  if (workspaces.length === 0) return null;
                  return (
                    <div className="min-w-0 flex-1 sm:min-w-[10rem] sm:max-w-[20rem]">
                      <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                        Workspace
                      </label>
                      <select
                        className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                        value={selectedWorkspaceId ?? ""}
                        onChange={(e) => setComposerWorkspace(e.target.value || null)}
                      >
                        {workspaces.map((ws) => (
                          <option key={ws.id} value={ws.id}>
                            {ws.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })()}
              </div>
              {(() => {
                const agent = visibleAgents.find((a) => a.id === selectedAgentId);
                if (!agent?.requires_workspace) return null;
                if (workspaces.length > 0) return null;
                return (
                  <div className="rounded-lg border border-surface-border bg-black/25 px-3 py-2">
                    <p className="text-xs leading-snug text-surface-muted">
                      No workspace yet. Create one on the Coding Agent page (manual folder or Git), then return here and
                      pick it from the list.
                    </p>
                    <NavLink
                      to="/coding-agent"
                      className="mt-2 inline-flex items-center justify-center rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
                    >
                      Open Coding Agent
                    </NavLink>
                  </div>
                );
              })()}
              {selectedAgentId === "coding" ? (
                <p className="max-w-xl text-[11px] leading-snug text-sky-300/85">
                  Tip: the model can call{" "}
                  <code className="rounded bg-black/30 px-1 text-neutral-300">coding_task</code> with{" "}
                  <code className="rounded bg-black/30 px-1 text-neutral-300">run_plan_subagent: true</code> to run a
                  short read-only <span className="text-neutral-200">coding_plan</span> pass on this workspace; the
                  tool JSON includes <code className="rounded bg-black/30 px-1 text-neutral-300">assistant_excerpt</code>.
                </p>
              ) : null}
              {selectedAgentId === "coding_plan" ? (
                <p className="max-w-xl text-[11px] leading-snug text-amber-200/90">
                  Read-only agent: no write, shell, or patch tools. Choose{" "}
                  <span className="text-neutral-200">Coding</span> to apply changes.
                </p>
              ) : null}
              <p className="text-[10px] leading-snug text-surface-muted">
                Titles from the first message. Open a shared chat: URL query{" "}
                <code className="text-neutral-500">?c=&lt;id&gt;</code>. From Dashboards:{" "}
                <code className="text-neutral-500">?dashboard=&lt;uuid&gt;</code> sends{" "}
                <code className="text-neutral-500">agent_dashboard_context</code> to the agent.
              </p>
            </div>
            <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-surface-border lg:pl-4">
              <SessionRuntimeBar
                runtime={sessionRuntime}
                usage={tokenUsage}
                className="w-full"
                mcpAddon={
                  selectedWorkspaceId &&
                  visibleAgents.find((a) => a.id === selectedAgentId)?.requires_workspace &&
                  selectedWorkspace &&
                  selectedWorkspace.access_role !== "viewer" ? (
                    <button
                      type="button"
                      className="ml-0.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-white/15 px-1 text-[11px] font-medium text-sky-300/95 hover:bg-white/10"
                      title="Edit MCP servers for this workspace only"
                      onClick={() => setShowWorkspaceMcpModal(true)}
                    >
                      +
                    </button>
                  ) : null
                }
              />
              <div className="w-full">
                <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                  Reply mode
                </label>
                <select
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as ChatMode)}
                  title="Agent: tools + multi-round WebSocket. Chat: single streamed assistant message (HTTP)."
                >
                  <option value="agent">Agent (tools, WebSocket)</option>
                  <option value="chat">Chat (streamed HTTP)</option>
                </select>
                <p className="mt-1 text-[10px] leading-snug text-surface-muted">
                  Chat mode sends <code className="text-neutral-500">agent_plain_completion</code> so tokens stream when
                  the model supports it.
                </p>
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
                        ? "Nur im Agent-Modus (WebSocket): LLM-Streaming pro Runde."
                        : "LLM-Antwort pro Runde streamen (wenn der Provider es unterstützt). Aus = bisheriges Verhalten."
                    }
                  />
                  <span>Agent: LLM-Stream</span>
                </label>
                <p className="mt-1 pl-6 text-[10px] leading-snug text-surface-muted">
                  Schaltet <code className="text-neutral-500">agent_stream_llm</code> ein. Bei Tools: sichtbarer Text bis
                  zum Tool-Call; weitere Runden folgen.
                </p>
              </div>
              <div className="w-full">
                <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">Model</label>
                <select
                  className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                  value={modelSelectValue || defaultSelectValue}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={!modelsCatalogReady || modelRows.length === 0}
                >
                  {!modelsCatalogReady ? (
                    <option value="">Loading models…</option>
                  ) : modelRows.length === 0 ? (
                    <option value="">
                      {formatEmptyChatModelCatalogHint(modelCatalogAgentlayer) ??
                        modelsCatalogHint ??
                        "No chat models available."}
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
        </div>

        {dashboardChatId ? (
          <div className="shrink-0 border-b border-sky-900/40 bg-sky-950/25 px-6 py-2 text-sm text-sky-100/90">
            <span className="font-medium text-sky-200">Dashboard context</span>
            {": "}
            {dashboardChatTitle ?? dashboardChatId}
            <span className="ml-2 text-xs text-sky-300/80">
              (this dashboard id is passed to the agent; say &quot;add milk&quot; for this list)
            </span>
          </div>
        ) : null}

        {activeThread?.dashboardId && activeThread.shared ? (
          <div
            className="shrink-0 border-b border-amber-900/45 bg-amber-950/40 px-6 py-2.5 text-sm text-amber-50/95"
            role="status"
          >
            <span className="font-medium text-amber-200">Shared dashboard chat</span>
            {" — "}
            Other members who can access this dashboard may see messages you send here. Do not post secrets or
            private data.
          </div>
        ) : null}

        {activeThread?.dashboardId && activeThread.shared !== true ? (
          <div
            className="shrink-0 border-b border-emerald-900/35 bg-emerald-950/25 px-6 py-2 text-sm text-emerald-100/90"
            role="status"
          >
            <span className="font-medium text-emerald-200">Personal dashboard chat</span>
            {" — "}
            Only your account sees this thread; it is not the shared team chat for this dashboard.
          </div>
        ) : null}

        {error ? (
          <div className="shrink-0 border-b border-red-900/50 bg-red-950/40 px-6 py-2 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
          <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-6 py-6">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-full border border-surface-border bg-white/5 text-lg font-semibold text-neutral-300">
                  AL
                </div>
                <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">
                  Hello, {displayName}
                </h1>
                <p className="mt-2 max-w-md text-sm text-surface-muted">
                  Agent mode: WebSocket with tools and activity on the right. Chat mode: streamed plain replies over HTTP
                  (no tools).
                </p>
              </div>
            ) : (
              <ul className="mx-auto flex w-full max-w-3xl flex-col gap-3">
                {messages.filter(chatMessageHasVisibleContent).map((m, i) => (
                  <li
                    key={`${i}-${m.role}-${m.content.slice(0, 24)}`}
                    className={`flex w-full ${m.role === "user" ? "justify-start" : "justify-end"}`}
                  >
                    <div
                      className={`max-w-[min(100%,42rem)] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                        m.role === "user"
                          ? "border border-sky-900/40 bg-[#1a2a3d] text-neutral-100"
                          : "border border-white/10 bg-[#1e1e1e] text-neutral-200"
                      }`}
                    >
                      <span className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                        {m.role === "user" ? "You" : "Assistant"}
                        <span className="ml-2 font-normal normal-case">
                          {new Date(m.timestamp ?? Date.now()).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                      </span>
                      {m.role === "user" ? (
                        <MessageBody content={m.content} />
                      ) : (
                        <div className="whitespace-pre-wrap">{m.content}</div>
                      )}
                    </div>
                  </li>
                ))}
                {loading &&
                !(
                  messages.length > 0 &&
                  messages[messages.length - 1]?.role === "assistant" &&
                  chatMessageHasVisibleContent(messages[messages.length - 1]!)
                ) ? (
                  <li className="flex w-full justify-end">
                    <div className="max-w-[min(100%,42rem)] rounded-2xl border border-sky-900/50 bg-sky-950/25 px-4 py-3 text-sm text-sky-100/90 shadow-sm">
                      <span className="mb-1 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-sky-300/80">
                        <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-sky-400" />
                        Assistant
                      </span>
                      <p className="text-neutral-300">
                        {mode === "agent" ? "Agent running (LLM / tools)…" : "Generating a reply…"}
                      </p>
                    </div>
                  </li>
                ) : null}
              </ul>
            )}
            <div ref={messagesEndRef} className="h-px w-full shrink-0" aria-hidden />
          </div>

          {mode === "agent" && agentLog.length > 0 ? (
            <div className="flex min-h-0 w-full shrink-0 flex-col border-t border-surface-border bg-black/20 lg:w-[300px] lg:border-l lg:border-t-0">
              <div className="shrink-0 border-b border-surface-border px-3 py-2 text-xs font-medium uppercase tracking-wide text-surface-muted">
                Agent activity
              </div>
              <ul className="min-h-0 flex-1 overflow-y-auto px-3 py-2 text-xs">
                {agentLog.map((e) => (
                  <li key={e.id} className="mb-2 border-l-2 border-sky-500/40 pl-2 text-neutral-400">
                    <span className="text-[10px] text-surface-muted">{e.kind}</span>
                    <div className="whitespace-pre-wrap text-neutral-300">{e.text}</div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <div className="shrink-0 border-t border-surface-border bg-[#0c0c0c] px-6 py-4">
          <div className="relative mx-auto max-w-3xl">
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
              aria-label="Message composer — drop files here or use the attach button"
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
                if (loading) return;
                void addPickedFiles(e.dataTransfer.files);
              }}
            >
              {composerDragActive ? (
                <div
                  className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-sky-950/50 backdrop-blur-[1px]"
                  aria-hidden
                >
                  <p className="rounded-lg border border-sky-500/40 bg-black/50 px-4 py-2 text-sm font-medium text-sky-100">
                    Drop files to attach
                  </p>
                </div>
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
                        {a.kind === "unsupported" ? " (not sent)" : ""}
                      </span>
                      <button
                        type="button"
                        className="shrink-0 rounded px-1 text-surface-muted hover:text-white"
                        aria-label="Remove attachment"
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
                placeholder="How can I help you today?"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={2}
                disabled={loading}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (canSend) onSend();
                  }
                }}
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <button
                  type="button"
                  disabled={loading}
                  className="rounded-lg border border-white/10 bg-black/20 p-2 text-surface-muted hover:bg-white/5 hover:text-neutral-200 disabled:opacity-40"
                  title="Attach or drag & drop files (images, text; zip not unpacked)"
                  aria-label="Attach files"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                </button>
                {loading ? (
                  <button
                    type="button"
                    className="rounded-lg border border-amber-500/60 bg-amber-950/50 px-4 py-2 text-sm font-medium text-amber-100 hover:bg-amber-900/40"
                    onClick={() => onCancelInFlight()}
                  >
                    Cancel
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={!canSend}
                    className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-40"
                    onClick={() => onSend()}
                  >
                    Send
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
                  {SUGGESTED.map((s) => (
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
              const agent = visibleAgents.find((a) => a.id === selectedAgentId);
              const wsParam =
                agent?.requires_workspace && selectedWorkspaceId ? selectedWorkspaceId : null;
              setSessionRuntime(await fetchSessionRuntime(auth, wsParam));
            } catch {
              /* ignore */
            }
          }}
        />
      ) : null}
    </div>
  );
}
