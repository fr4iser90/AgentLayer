import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import i18n from "../i18n/config";
import { useAuth } from "../auth/AuthContext";
import {
  type AgentTimelineEntry,
  type ChatThread,
  type UiMessage,
  newMessageId,
} from "../features/chat/chatThreadStorage";
import {
  activityForTurn,
  appendTimelineEntry,
  archiveTurnBeforeNewPrompt,
  latestUserMessageId,
  serializeAgentLogPayload,
} from "../features/chat/agentLogStorage";
import { AgentActivityPanel } from "../features/chat/AgentActivityPanel";
import {
  getShowSubagentsInActivity,
  setShowSubagentsInActivity as persistShowSubagentsPref,
} from "../features/chat/chatSubagentPrefs";
import { handleSubagentWsEvent } from "../features/chat/subagentActivity";
import { TurnNavigator, TurnNavigatorHorizontal, buildTurnItems } from "../features/chat/TurnNavigator";
import { useChatScroll } from "../features/chat/useChatScroll";
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
  parseContentParts,
  toApiContent,
} from "../features/chat/messageFormat";
import { getDisabledToolNames } from "../features/settings/toolPrefs";
import { getAgentStreamLlm, setAgentStreamLlm } from "../features/settings/agentStreamPrefs";
import {
  buildBuildSidebarGroups,
  filterThreadsForBuildSidebar,
  threadsVisibleInSidebar,
} from "../features/chat/groupThreadsForSidebar";
import {
  extractProposals,
  stripProposalBlocks,
  formatOptionSelection,
  type Proposal,
  type ProposalOption,
} from "../lib/proposalParser";
import {
  addUsageTotals,
  apiFetch,
  emptyTokenUsage,
  fetchSessionRuntime,
  type SessionRuntimePayload,
  type TokenUsageTotals,
  type WorkspaceApiRecord,
} from "../lib/api";
import { SessionRuntimeBar } from "../features/chat/SessionRuntimeBar";
import { CodingWorkspacePanels } from "../features/workspace/CodingWorkspacePanels";
import { WorkspaceMcpModal } from "../features/workspace/WorkspaceMcpModal";
import { WorkspaceRetrievalBar } from "../features/workspace/WorkspaceRetrievalBar";
import { shouldIsolateWorkspaceThread } from "../features/workspace/codingWorkspaceNav";
import {
  applyModelCatalogSelection,
  defaultModelCatalogSelectValue,
  fetchModelCatalog,
  embeddingModelOptions,
  formatEmbeddingStatusHint,
  formatEmptyChatModelCatalogHint,
  formatModelCatalogHint,
  patchEmbeddingModel,
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

async function fetchWorkspaces(auth: ReturnType<typeof useAuth>): Promise<WorkspaceApiRecord[]> {
  const r = await apiFetch("/v1/workspaces", auth);
  if (!r.ok) return [];
  const j = (await r.json()) as { workspaces: WorkspaceApiRecord[] };
  return j.workspaces ?? [];
}

async function createWorkspace(auth: ReturnType<typeof useAuth>, name: string, gitUrl?: string) {
  const r = await apiFetch("/v1/workspaces", auth, {
    method: "POST",
    body: JSON.stringify({
      name,
      source: gitUrl ? "git" : "manual",
      git_url: gitUrl ?? null,
      git_branch: "main",
    }),
  });
  if (!r.ok) {
    const err = (await r.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? i18n.t("coding:createWorkspaceFailed"));
  }
  const j = (await r.json()) as { workspace: WorkspaceApiRecord };
  return j.workspace;
}

async function deleteWorkspace(auth: ReturnType<typeof useAuth>, workspaceId: string) {
  const r = await apiFetch(`/v1/workspaces/${workspaceId}`, auth, { method: "DELETE" });
  if (!r.ok) {
    const err = (await r.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? i18n.t("coding:deleteWorkspaceFailed"));
  }
  return true;
}

async function resetSelfWorkspaceApi(
  auth: ReturnType<typeof useAuth>,
  workspaceId: string,
  body: { backup_existing: boolean }
): Promise<WorkspaceApiRecord> {
  const r = await apiFetch(`/v1/workspaces/${workspaceId}/self/reset`, auth, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const j = (await r.json().catch(() => ({}))) as { ok?: boolean; workspace?: WorkspaceApiRecord; detail?: string };
  if (!r.ok) {
    const d = typeof j.detail === "string" ? j.detail : `HTTP ${r.status}`;
    throw new Error(d);
  }
  if (!j.workspace) {
    throw new Error(i18n.t("coding:resetNoPayload"));
  }
  return j.workspace;
}

async function createImplementationBranchApi(
  auth: ReturnType<typeof useAuth>,
  workspaceId: string,
  body: { base_branch?: string; implementation_run_id?: string }
): Promise<{ branch: string; base_branch?: string; head_summary?: string }> {
  const r = await apiFetch(`/v1/workspaces/${workspaceId}/git/implementation-branch`, auth, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const j = (await r.json().catch(() => ({}))) as {
    branch?: string;
    base_branch?: string;
    head_summary?: string;
    detail?: string;
  };
  if (!r.ok) {
    const d = typeof j.detail === "string" ? j.detail : `HTTP ${r.status}`;
    throw new Error(d);
  }
  if (!j.branch) {
    throw new Error(i18n.t("coding:branchNoName"));
  }
  return { branch: j.branch, base_branch: j.base_branch, head_summary: j.head_summary };
}


function wsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/v1/chat?token=${encodeURIComponent(token)}`;
}

function assistantFromCompletion(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const d = data as {
    choices?: Array<{ message?: { content?: unknown; tool_calls?: unknown } }>;
  };
  const msg0 = d.choices?.[0]?.message;
  const c = msg0?.content;
  let text = "";
  if (typeof c === "string") text = c;
  else if (Array.isArray(c)) {
    text = c
      .map((part: unknown) => {
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text?: string }).text ?? "");
        }
        return "";
      })
      .join("");
  }
  return text;
}

function chatMessageHasVisibleContent(m: UiMessage): boolean {
  const raw = m.content ?? "";
  if (m.role === "assistant" && extractProposals(raw).length > 0) return true;
  return raw.trim().length > 0;
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
  const plain = stripProposalBlocks(content);
  const { parts } = parseContentParts(plain);
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

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80 ? "text-emerald-300" : pct >= 60 ? "text-amber-300" : "text-red-300";
  return <span className={`text-[10px] font-medium ${color}`}>{pct}%</span>;
}

function ProposalCard({
  proposal,
  selected,
  onSelect,
}: {
  proposal: Proposal;
  selected: string | null;
  onSelect: (option: ProposalOption) => void;
}) {
  return (
    <div className="my-4 rounded-xl border border-sky-800/40 bg-[#111827] shadow-lg">
      <div className="border-b border-sky-800/30 px-4 py-3">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <h3 className="text-sm font-semibold text-sky-100">{proposal.title}</h3>
        </div>
      </div>
      <div className="p-3">
        <ul className="flex flex-col gap-2">
          {proposal.options.map((opt) => {
            const isSelected = selected === opt.id;
            return (
              <li key={opt.id}>
                <button
                  type="button"
                  className={`w-full rounded-lg border px-4 py-3 text-left transition-all ${
                    isSelected
                      ? "border-sky-500 bg-sky-950/50 ring-1 ring-sky-500/50"
                      : "border-surface-border bg-black/20 hover:border-sky-700/50 hover:bg-white/5"
                  }`}
                  onClick={() => onSelect(opt)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold ${
                          isSelected
                            ? "border-sky-400 bg-sky-500 text-white"
                            : "border-surface-border text-surface-muted"
                        }`}
                      >
                        {isSelected ? "✓" : proposal.options.indexOf(opt) + 1}
                      </span>
                      <span className="text-sm font-medium text-neutral-200">
                        {opt.label}
                      </span>
                    </div>
                    {opt.confidence != null && (
                      <ConfidenceBadge value={opt.confidence} />
                    )}
                  </div>
                  {opt.description && (
                    <p className="mt-1.5 pl-7 text-xs leading-relaxed text-neutral-400">
                      {opt.description}
                    </p>
                  )}
                  {opt.actions && opt.actions.length > 0 && (
                    <ul className="mt-2 pl-7">
                      {opt.actions.map((action, ai) => (
                        <li key={ai} className="flex items-center gap-1.5 text-[11px] text-neutral-500">
                          <span className="text-sky-500/70">→</span>
                          {action}
                        </li>
                      ))}
                    </ul>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="border-t border-sky-800/30 px-4 py-2">
        <p className="text-[10px] text-surface-muted">
          Click an option to tell the agent how to proceed
        </p>
      </div>
    </div>
  );
}

const CODING_TOOLS = [
  "coding_apply_patch",
  "coding_bash",
  "coding_edit",
  "coding_git_read",
  "coding_git_sync",
  "coding_git_push",
  "coding_glob",
  "coding_index",
  "coding_list_dir",
  "coding_lsp",
  "coding_read_file",
  "coding_replace",
  "coding_search",
  "coding_semantic_search",
  "coding_symbols",
  "coding_task",
  "coding_todo",
  "coding_workspace_verify",
  "coding_write_file",
  "project_explain",
  "workspace_bind",
  "workspace_create",
  "workspace_list",
];

/** Plan tab uses the same coding tool names as Build; server + WebSocket handle permission ask. */
const CODING_PLAN_TOOL_NAMES = CODING_TOOLS;

type CodingSessionMode = "build" | "plan";

/** When switching Plan → Build with a transcript: how to handle `agent/impl-…` on the server. */
type ImplBranchPreference = "ask" | "always" | "never";

type PermAskGate = { requestId: string; toolName: string; argsPreview: string };

function codingModeStorageKey(userId: string, threadId: string): string {
  return `agentlayer.coding.mode.v1:${userId}:${threadId}`;
}

function implBranchPrefStorageKey(userId: string): string {
  return `agentlayer.coding.implBranch.v1:${userId}`;
}

function parseImplBranchPref(raw: string | null): ImplBranchPreference {
  if (raw === "always" || raw === "never") return raw;
  return "ask";
}

function ImplementationBranchSetting({
  value,
  onChange,
  className = "",
}: {
  value: ImplBranchPreference;
  onChange: (v: ImplBranchPreference) => void;
  className?: string;
}) {
  const { t } = useTranslation(["coding"]);
  return (
    <div className={`mt-2 flex flex-col gap-1 text-left ${className}`}>
      <label
        className="text-[10px] font-medium uppercase tracking-wide text-surface-muted"
        htmlFor="impl-branch-pref"
      >
        {t("coding:implBranchLabel")}
      </label>
      <select
        id="impl-branch-pref"
        className="max-w-xs rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-neutral-200"
        value={value}
        onChange={(e) => onChange(e.target.value as ImplBranchPreference)}
      >
        <option value="ask">{t("coding:implBranchAsk")}</option>
        <option value="always">{t("coding:implBranchAlways")}</option>
        <option value="never">{t("coding:implBranchNever")}</option>
      </select>
      <p className="text-[10px] leading-snug text-surface-muted">{t("coding:implBranchHint")}</p>
    </div>
  );
}

function CodingBuildPlanToggle({
  mode,
  onChange,
  helper,
  className = "",
}: {
  mode: CodingSessionMode;
  onChange: (m: CodingSessionMode) => void;
  helper?: string;
  className?: string;
}) {
  const { t } = useTranslation(["coding"]);
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">{t("coding:modeLabel")}</span>
        <div className="inline-flex rounded-lg border border-surface-border bg-black/40 p-0.5">
          <button
            type="button"
            onClick={() => onChange("build")}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "build" ? "bg-sky-600 text-white shadow" : "text-surface-muted hover:text-white"
            }`}
          >
            {t("coding:modeBuild")}
          </button>
          <button
            type="button"
            onClick={() => onChange("plan")}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "plan" ? "bg-amber-600 text-white shadow" : "text-surface-muted hover:text-white"
            }`}
          >
            {t("coding:modePlan")}
          </button>
        </div>
      </div>
      {helper ? <p className="text-[10px] leading-snug text-surface-muted">{helper}</p> : null}
    </div>
  );
}

export function CodingAgentPage() {
  const { t } = useTranslation(["coding", "errors", "chat", "workspace", "setup"]);
  const codingSuggested = useMemo(
    () => [
      t("coding:suggested1"),
      t("coding:suggested2"),
      t("coding:suggested3"),
      t("coding:suggested4"),
    ],
    [t]
  );
  const auth = useAuth();
  const { accessToken, user } = auth;
  const userId = user?.id ?? "";
  const isAdminUser = (user?.role ?? "").toLowerCase() === "admin";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkRef = useRef<{ workspaceId: string; newSession: boolean } | null>(null);

  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelRows, setModelRows] = useState<ModelRow[]>([]);
  const [modelsCatalogReady, setModelsCatalogReady] = useState(false);
  const [modelsCatalogHint, setModelsCatalogHint] = useState<string | null>(null);
  const [modelCatalogAgentlayer, setModelCatalogAgentlayer] = useState<ModelCatalogAgentlayer | null>(null);
  const embeddingMeta = modelCatalogAgentlayer?.embedding as EmbeddingCatalogHealth | undefined;
  const embeddingModelRows = useMemo(() => embeddingModelOptions(embeddingMeta), [embeddingMeta]);
  const embeddingStatusHint = useMemo(() => formatEmbeddingStatusHint(embeddingMeta), [embeddingMeta]);
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [embeddingModelSaving, setEmbeddingModelSaving] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [selectedOptions, setSelectedOptions] = useState<Map<string, { proposal: Proposal; option: ProposalOption }>>(new Map());

  const [workspaces, setWorkspaces] = useState<WorkspaceApiRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [workspacesLoading, setWorkspacesLoading] = useState(false);
  const [showCreateWorkspace, setShowCreateWorkspace] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [newWorkspaceGitUrl, setNewWorkspaceGitUrl] = useState("");
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  const [sessionMode, setSessionMode] = useState<CodingSessionMode>("build");
  const [agentStreamLlmUi, setAgentStreamLlmUi] = useState(() => getAgentStreamLlm());
  const [permAsk, setPermAsk] = useState<PermAskGate | null>(null);
  const [implBranchPreference, setImplBranchPreferenceState] = useState<ImplBranchPreference>("ask");
  const [sessionRuntime, setSessionRuntime] = useState<SessionRuntimePayload | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsageTotals>(() => emptyTokenUsage());
  const [showWorkspaceMcpModal, setShowWorkspaceMcpModal] = useState(false);
  const [changesRefreshKey, setChangesRefreshKey] = useState(0);
  const [showSubagentsInActivity, setShowSubagentsInActivity] = useState(true);

  const setImplBranchPreference = useCallback(
    (v: ImplBranchPreference) => {
      setImplBranchPreferenceState(v);
      if (userId) {
        localStorage.setItem(implBranchPrefStorageKey(userId), v);
      }
    },
    [userId]
  );

  useEffect(() => {
    if (!userId) return;
    setImplBranchPreferenceState(parseImplBranchPref(localStorage.getItem(implBranchPrefStorageKey(userId))));
  }, [userId]);

  useEffect(() => {
    if (!userId || !activeThreadId) return;
    const raw = localStorage.getItem(codingModeStorageKey(userId, activeThreadId));
    setSessionMode(raw === "plan" ? "plan" : "build");
  }, [userId, activeThreadId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const r = await fetchSessionRuntime(auth, selectedWorkspaceId);
      if (!cancelled) setSessionRuntime(r);
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, selectedWorkspaceId]);

  const applyCodingSessionMode = useCallback(
    (m: CodingSessionMode) => {
      setSessionMode(m);
      if (userId && activeThreadId) {
        localStorage.setItem(codingModeStorageKey(userId, activeThreadId), m);
      }
      const aid = m === "plan" ? "coding_plan" : "coding";
      if (activeThreadId) {
        setThreads((prev) => {
          const next = prev.map((t) =>
            t.id === activeThreadId ? { ...t, agentId: aid, updatedAt: Date.now() } : t
          );
          const th = next.find((x) => x.id === activeThreadId);
          if (th) void putConversation(auth, th).catch(() => {});
          return next;
        });
      }
    },
    [userId, activeThreadId, auth]
  );

  const wsRef = useRef<WebSocket | null>(null);
  const agentHandlerRef = useRef<(ev: MessageEvent) => void>(() => {});
  /** User cancelled before the chat frame was sent (e.g. while WebSocket connects). */
  const cancelAgentTurnRef = useRef(false);
  const activeThreadIdRef = useRef<string | null>(null);
  const lastModelSelectionRef = useRef("");
  /** Prepended to the next user message after Plan→Build + server implementation-branch creation. */
  const implementationBranchPreambleRef = useRef<string | null>(null);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const toolStartTimesRef = useRef<Map<string, number>>(new Map());
  const subagentStartTimesRef = useRef<Map<string, number>>(new Map());
  const agentTurnBaselineRef = useRef<UiMessage[] | null>(null);
  const streamDeltaAccRef = useRef("");
  const agentStreamEnabledThisTurnRef = useRef(false);
  activeThreadIdRef.current = activeThreadId;

  const displayName = useMemo(() => {
    const e = user?.email;
    if (!e) return "there";
    return e.split("@")[0] ?? "there";
  }, [user?.email]);

  const activeThread = useMemo(
    () => threads.find((t) => t.id === activeThreadId) ?? null,
    [threads, activeThreadId]
  );

  const selectCodingSession = useCallback(
    async (id: string) => {
      setActiveThreadId(id);
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
    [auth]
  );

  useEffect(() => {
    if (!activeThreadId || !workspaces.length) return;
    const thread = threads.find((x) => x.id === activeThreadId);
    if (!thread) return;
    const wid = typeof thread.workspaceId === "string" && thread.workspaceId.trim() ? thread.workspaceId.trim() : null;
    if (wid && workspaces.some((w) => w.id === wid)) {
      setSelectedWorkspaceId(wid);
    }
  }, [activeThreadId, threads, workspaces]);

  const messages = activeThread?.messages ?? [];
  const lastMessage = messages[messages.length - 1];

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

  const activityLoading = loading && selectedTurnId === latestTurnId;

  const handleSelectTurn = useCallback((userMessageId: string) => {
    setSelectedTurnId(userMessageId);
    document.getElementById(`msg-${userMessageId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, []);
  const showAgentRunningPlaceholder =
    loading &&
    !(
      lastMessage?.role === "assistant" &&
      chatMessageHasVisibleContent(lastMessage)
    );

  const defaultSelectValue = useMemo(
    () => defaultModelCatalogSelectValue(modelRows),
    [modelRows]
  );
  const defaultModel = useMemo(() => {
    const p = parseModelCatalogSelection(defaultSelectValue);
    return p.modelId || modelRows[0]?.id || "";
  }, [defaultSelectValue, modelRows]);
  const modelSelectValue = useMemo(
    () =>
      composerSelectValueForThread(
        modelRows,
        activeThread?.model ?? "",
        activeThread?.modelProvider,
        defaultSelectValue
      ),
    [activeThread?.model, activeThread?.modelProvider, defaultSelectValue, modelRows]
  );

  useEffect(() => {
    if (modelSelectValue.includes(":")) {
      lastModelSelectionRef.current = modelSelectValue;
    }
  }, [modelSelectValue]);

  useEffect(() => {
    setHydrated(false);
  }, [userId]);

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
    setThreads((prev) =>
      prev.map((t) =>
        t.id === activeThreadId
          ? { ...t, model: routed.model, modelProvider: routed.provider, updatedAt: Date.now() }
          : t
      )
    );
  }, [activeThreadId, defaultSelectValue, modelsCatalogReady, modelRows, threads]);

  useEffect(() => {
    const m = (embeddingMeta?.model ?? "").trim();
    if (m) setEmbeddingModel(m);
  }, [embeddingMeta?.model, modelsCatalogReady]);

  const refreshModelCatalog = useCallback(async () => {
    const { rows, agentlayer } = await fetchModelCatalog();
    setModelRows(rows);
    setModelCatalogAgentlayer(agentlayer);
    setModelsCatalogHint(formatModelCatalogHint(agentlayer, { excludeUnreachableProviderHints: true }));
    const sel = (agentlayer?.embedding as EmbeddingCatalogHealth | undefined)?.model?.trim();
    if (sel) setEmbeddingModel(sel);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        if (cancelled) return;
        await refreshModelCatalog();
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
    return () => { cancelled = true; };
  }, [refreshModelCatalog]);

  const setEmbeddingModelSelection = useCallback(
    async (modelId: string) => {
      const id = modelId.trim();
      if (!id) return;
      setEmbeddingModel(id);
      if (!isAdminUser) return;
      setEmbeddingModelSaving(true);
      try {
        const hintDim = embeddingMeta?.actual_embedding_dim ?? embeddingMeta?.embedding_dim;
        const { ok } = await patchEmbeddingModel(auth, id, {
          embeddingDim: typeof hintDim === "number" ? hintDim : undefined,
        });
        if (ok) await refreshModelCatalog();
        else setError(t("coding:embeddingModelSaveNoAdmin"));
      } catch {
        setError(t("coding:embeddingModelSaveFailed"));
      } finally {
        setEmbeddingModelSaving(false);
      }
    },
    [auth, embeddingMeta?.actual_embedding_dim, embeddingMeta?.embedding_dim, isAdminUser, refreshModelCatalog]
  );

  useEffect(() => {
    if (!accessToken || !userId) return;
    let cancelled = false;
    void (async () => {
      try {
        const ws = await fetchWorkspaces(auth);
        if (cancelled) return;
        setWorkspaces(ws);
        setSelectedWorkspaceId((prev) => {
          if (prev && ws.some((w) => w.id === prev)) return prev;
          return ws[0]?.id ?? null;
        });
      } catch {
        /* ignore */
      }
    })();
    return () => { cancelled = true; };
  }, [accessToken, userId, auth]);

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
          setHydrated(true);
          return;
        }
        const mapped = listRaw.map((row) => mapListItemToThread(row as Record<string, unknown>));
        setThreads(mapped);
        const buildMapped = filterThreadsForBuildSidebar(mapped);
        const withMsgs = buildMapped.find((x) => (x.messageCount ?? x.messages.length) > 0);
        const pick = withMsgs?.id ?? buildMapped[0]?.id ?? null;
        if (!pick) { setActiveThreadId(null); setHydrated(true); return; }
        setActiveThreadId(pick);
        const full = await fetchConversationDetail(auth, pick);
        if (cancelled) return;
        setThreads((prev) =>
          prev.map((th) => (th.id === full.id ? mergeServerThreadWithLocal(full, th) : th))
        );
        setHydrated(true);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : t("errors:loadChatsFailed"));
          setHydrated(true);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [accessToken, userId, auth]);

  useEffect(() => {
    if (!userId) return;
    setShowSubagentsInActivity(getShowSubagentsInActivity(userId));
  }, [userId]);

  const appendAgentLine = useCallback(
    (
      kind: string,
      text: string,
      extras?: Pick<
        AgentTimelineEntry,
        "toolName" | "durationMs" | "resultChars" | "subagentAgentId" | "nested"
      >
    ) => {
      const tid = activeThreadIdRef.current;
      if (!tid) return;
      setThreads((prev) =>
        prev.map((t) => {
          if (t.id !== tid) return t;
          const next = appendTimelineEntry(t.agentLog ?? [], { kind, text, ...extras });
          return { ...t, agentLog: next, updatedAt: Date.now() };
        })
      );
    },
    []
  );

  const handleCodingSessionModeChange = useCallback(
    async (m: CodingSessionMode) => {
      if (
        m === "build" &&
        sessionMode === "plan" &&
        activeThreadId &&
        selectedWorkspaceId
      ) {
        const thread = threads.find((x) => x.id === activeThreadId);
        const hasTranscript = (thread?.messages.length ?? 0) > 0;
        if (hasTranscript) {
          const ws = workspaces.find((w) => w.id === selectedWorkspaceId);
          const baseHint = (ws?.git_branch ?? "main").trim() || "main";
          let shouldCreate = false;
          if (implBranchPreference === "always") {
            shouldCreate = true;
          } else if (implBranchPreference === "never") {
            shouldCreate = false;
          } else {
            shouldCreate = window.confirm(
              t("coding:switchToBuildCreateBranchQuestion", { base: baseHint })
            );
          }
          if (shouldCreate) {
            setError(null);
            try {
              const runId =
                typeof crypto !== "undefined" && "randomUUID" in crypto
                  ? crypto.randomUUID()
                  : `${Date.now()}`;
              const j = await createImplementationBranchApi(auth, selectedWorkspaceId, {
                base_branch: baseHint,
                implementation_run_id: runId,
              });
              implementationBranchPreambleRef.current =
                `[Implementation: you are on a new git branch \`${j.branch}\` (created from \`${j.base_branch ?? baseHint}\`). ` +
                "Implement the agreed plan from this thread; keep commits on this branch.]\n\n";
              appendAgentLine(
                "session",
                `Git implementation branch: ${j.branch} ← ${j.base_branch ?? baseHint}`
              );
            } catch (e) {
              const msg = e instanceof Error ? e.message : String(e);
              setError(msg);
              const still = window.confirm(
                t("coding:createImplBranchFailedContinueQuestion")
              );
              if (!still) return;
            }
          }
        }
      }
      applyCodingSessionMode(m);
    },
    [
      implBranchPreference,
      activeThreadId,
      appendAgentLine,
      applyCodingSessionMode,
      auth,
      selectedWorkspaceId,
      sessionMode,
      threads,
      workspaces,
    ]
  );

  const ensureAgentWs = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const tok = accessToken;
      if (!tok) { reject(new Error(t("errors:notSignedIn"))); return; }
      const existing = wsRef.current;
      if (existing?.readyState === WebSocket.OPEN) { resolve(existing); return; }
      if (existing) { existing.close(); wsRef.current = null; }
      const ws = new WebSocket(wsUrl(tok));
      ws.onopen = () => { wsRef.current = ws; ws.onmessage = (ev) => agentHandlerRef.current(ev); resolve(ws); };
      ws.onerror = () => reject(new Error(t("errors:websocketFailed")));
      ws.onclose = () => { if (wsRef.current === ws) wsRef.current = null; };
    });
  }, [accessToken, t]);

  const runAgentWs = useCallback(async () => {
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
    const effectiveModel = routed.model;

    if (!selectedWorkspaceId) {
      setError(t("errors:selectWorkspaceBeforeSending"));
      return;
    }

    const preamble = implementationBranchPreambleRef.current;
    if (preamble) implementationBranchPreambleRef.current = null;
    const userContentRaw = buildUserMessageContent(draft, []);
    const userContent = preamble ? preamble + userContentRaw : userContentRaw;
    if (!userContent) return;

    const agentId = sessionMode === "plan" ? "coding_plan" : "coding";

    setError(null);
    setLoading(true);
    setTokenUsage(emptyTokenUsage());
    const firstUser = thread.messages.length === 0;
    const archivePatch = archiveTurnBeforeNewPrompt(thread);
    const userMsgId = newMessageId();
    const nextMessages: UiMessage[] = [
      ...thread.messages,
      { role: "user", content: userContent, id: userMsgId, createdAt: Date.now() },
    ];
    const nextTitle = firstUser ? draft.slice(0, 52) : thread.title;
    setThreads((prev) =>
      prev.map((th) =>
        th.id === tid
          ? {
              ...th,
              messages: nextMessages,
              ...archivePatch,
              title: nextTitle,
              model: effectiveModel,
              modelProvider: routed.provider,
              agentId: agentId,
              workspaceId: selectedWorkspaceId,
              updatedAt: Date.now(),
            }
          : th
      )
    );
    setSelectedTurnId(userMsgId);
    setDraft("");
    agentTurnBaselineRef.current = nextMessages;
    streamDeltaAccRef.current = "";
    agentStreamEnabledThisTurnRef.current = getAgentStreamLlm();

    cancelAgentTurnRef.current = false;

    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      setLoading(false);
      setPermAsk(null);
      setChangesRefreshKey((k) => k + 1);
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
        if (typ === "error") { setError(typeof msg.detail === "string" ? msg.detail : t("errors:agentError")); finish(); return; }
        if (typ === "chat.completion") {
          if (msg.error) { setError(typeof msg.detail === "string" ? msg.detail : t("coding:cancelledOrFailed")); finish(); return; }
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
          appendAgentLine("session", em ? `model: ${em}` : "");
          if (msg.workspace_bound === true && msg.workspace_id != null) {
            const wid = String(msg.workspace_id).trim();
            if (wid) {
              setSelectedWorkspaceId(wid);
              const tid = activeThreadIdRef.current;
              const th0 = threads.find((x) => x.id === tid);
              const msgCount = th0?.messageCount ?? th0?.messages.length ?? 0;
              if (msgCount > 2 && tid) {
                const wsName =
                  workspaces.find((w) => w.id === wid)?.name ?? t("coding:projectFallbackName");
                const openNew = window.confirm(t("coding:workspaceSwitchedConfirm", { name: wsName }));
                if (openNew) {
                  void startNewChat(wid);
                  return;
                }
              }
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
        if (typ === "agent.permission_ask") {
          const requestId = String(msg.request_id ?? "");
          const toolName = String(msg.tool_name ?? "tool");
          const argsPreview = String(msg.args_preview ?? "");
          if (requestId) {
            setPermAsk({ requestId, toolName, argsPreview });
            appendAgentLine("permission", t("coding:permissionWaiting", { tool: toolName }));
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
          appendAgentLine("llm", msg.round != null ? `round ${msg.round} (start)` : "round (start)");
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
          appendAgentLine("llm", msg.round != null ? `round ${msg.round}` : "round");
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
            subagentStartTimesRef.current
          )
        ) {
          return;
        }
        if (typ === "agent.tool_start") {
          const toolName = String(msg.name ?? "tool");
          toolStartTimesRef.current.set(toolName, Date.now());
          appendAgentLine("tool_start", `→ ${toolName}`, { toolName });
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
                ? `${durationMs}ms`
                : durationMs < 60000
                  ? `${(durationMs / 1000).toFixed(1)}s`
                  : `${(durationMs / 60000).toFixed(1)}m`
            );
          }
          appendAgentLine("tool_done", `${n}${parts.length ? ` (${parts.join(", ")})` : ""}`, {
            toolName: n,
            durationMs: durationMs ?? undefined,
            resultChars: ch,
          });
          return;
        }
        if (typ === "agent.done" || typ === "agent.aborted" || typ === "agent.cancelled") {
          appendAgentLine(typ, String(msg.detail ?? ""));
          finish();
          return;
        }
      } catch { setError(t("coding:invalidWebsocketMessage")); finish(); }
    };

    try {
      const ws = await ensureAgentWs();
      if (cancelAgentTurnRef.current) {
        cancelAgentTurnRef.current = false;
        finish();
        return;
      }
      const disabledTools = getDisabledToolNames();
      const toolBucket = sessionMode === "plan" ? CODING_PLAN_TOOL_NAMES : CODING_TOOLS;
      const enabledTools = toolBucket.filter((x) => !disabledTools.includes(x));
      ws.send(
        JSON.stringify({
          type: "chat",
          body: {
            model: effectiveModel,
            messages: nextMessages.map((m) => ({ role: m.role, content: toApiContent(m.content) })),
            agent_id: agentId,
            TOOL_DOMAIN: "coding",
            workspace_id: selectedWorkspaceId,
            ...(activeThreadId ? { conversation_id: activeThreadId } : {}),
            ...(enabledTools.length < toolBucket.length
              ? { agent_disabled_tools: disabledTools }
              : {}),
            agent_model_catalog_owned_by: routed.provider,
            agent_permission_ask: false,
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
    appendAgentLine,
    auth,
    defaultModel,
    draft,
    ensureAgentWs,
    modelRows,
    modelSelectValue,
    selectedWorkspaceId,
    sessionMode,
    threads,
  ]);

  const onSend = () => {
    void runAgentWs();
  };

  const onCancelInFlight = useCallback(() => {
    cancelAgentTurnRef.current = true;
    setLoading(false);
    setPermAsk(null);
    const w = wsRef.current;
    if (w?.readyState === WebSocket.OPEN) {
      try {
        w.send(JSON.stringify({ type: "cancel" }));
      } catch {
        /* ignore */
      }
    }
  }, []);

  const handleSelectOption = useCallback(
    (proposal: Proposal, option: ProposalOption) => {
      setSelectedOptions((prev) => {
        const next = new Map(prev);
        next.set(proposal.id, { proposal, option });
        return next;
      });
      const selectionMsg = formatOptionSelection(proposal, option);
      setDraft(selectionMsg);
      setTimeout(() => {
        void runAgentWs();
      }, 100);
    },
    [runAgentWs]
  );

  const startNewChat = useCallback(
    async (workspaceIdOverride?: string | null) => {
    try {
      const wsForChat = workspaceIdOverride ?? selectedWorkspaceId;
      const defaultProv = parseModelCatalogSelection(defaultSelectValue).provider;
      const title = t("coding:newBuildSessionTitle");
      const newThread = await createConversation(auth, {
        title,
        mode: "agent",
        model: defaultModel,
        messages: [],
        agent_log: serializeAgentLogPayload({ agentLog: [], turnLogs: [] }),
        agent_id: sessionMode === "plan" ? "coding_plan" : "coding",
        workspace_id: wsForChat,
        model_catalog_owned_by: defaultProv ?? null,
      });
      if (userId) {
        localStorage.setItem(codingModeStorageKey(userId, newThread.id), sessionMode);
      }
      setThreads((prev) => [newThread, ...prev]);
      setActiveThreadId(newThread.id);
      setDraft("");
      setError(null);
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  },
    [
      auth,
      defaultModel,
      defaultSelectValue,
      selectedWorkspaceId,
      sessionMode,
      userId,
    ]
  );

  const deleteThread = async (id: string) => {
    if (!confirm(t("coding:deleteBuildSessionConfirm"))) return;
    try {
      await deleteConversationApi(auth, id);
      setThreads((prev) => {
        const next = prev.filter((t) => t.id !== id);
        if (next.length === 0) { setActiveThreadId(null); return []; }
        if (id === activeThreadId) setActiveThreadId(next[0].id);
        return next;
      });
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  const handleCreateWorkspace = async () => {
    if (!newWorkspaceName.trim()) return;
    setCreatingWorkspace(true);
    try {
      const ws = await createWorkspace(auth, newWorkspaceName.trim(), newWorkspaceGitUrl.trim() || undefined);
      setWorkspaces((prev) => [...prev, ws]);
      setSelectedWorkspaceId(ws.id);
      setShowCreateWorkspace(false);
      setNewWorkspaceName("");
      setNewWorkspaceGitUrl("");
    } catch (e) {
      setError(e instanceof Error ? e.message : t("coding:createWorkspaceFailed"));
    } finally {
      setCreatingWorkspace(false);
    }
  };

  const handleDeleteWorkspace = async (wsId: string) => {
    if (!confirm(t("coding:deleteWorkspaceConfirm"))) return;
    try {
      await deleteWorkspace(auth, wsId);
      setWorkspaces((prev) => prev.filter((w) => w.id !== wsId));
      if (selectedWorkspaceId === wsId) {
        setSelectedWorkspaceId(workspaces.length > 1 ? workspaces.find((w) => w.id !== wsId)?.id ?? null : null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("coding:deleteWorkspaceFailed"));
    }
  };

  const handleResetSelfWorkspace = async (
    wsId: string,
    opts: { backupExisting: boolean }
  ) => {
    const { backupExisting } = opts;
    const first = confirm(t("coding:resetSelfConfirm"));
    if (!first) return;
    if (!backupExisting) {
      const sure = confirm(t("coding:resetNoBackupConfirm"));
      if (!sure) return;
    }
    try {
      const ws = await resetSelfWorkspaceApi(auth, wsId, { backup_existing: backupExisting });
      setWorkspaces((prev) => prev.map((w) => (w.id === ws.id ? ws : w)));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("coding:resetSelfFailed"));
    }
  };

  const selectedWorkspace = useMemo(
    () => workspaces.find((w) => w.id === selectedWorkspaceId) ?? null,
    [workspaces, selectedWorkspaceId]
  );

  const renameThread = (id: string) => {
    const thread = threads.find((x) => x.id === id);
    if (!thread) return;
    const next = window.prompt(t("coding:renameSessionPrompt"), thread.title);
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed) return;
    setThreads((prev) =>
      prev.map((th) => (th.id === id ? { ...th, title: trimmed, updatedAt: Date.now() } : th))
    );
    void putConversation(auth, { ...thread, title: trimmed }).catch(() => {});
  };

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

  useEffect(() => {
    const wsParam = (searchParams.get("workspace") || "").trim();
    if (!wsParam) return;
    deepLinkRef.current = {
      workspaceId: wsParam,
      newSession: searchParams.get("new") === "1",
    };
  }, [searchParams]);

  useEffect(() => {
    const pending = deepLinkRef.current;
    if (!pending || workspaces.length === 0 || !hydrated) return;
    if (!workspaces.some((w) => w.id === pending.workspaceId)) {
      deepLinkRef.current = null;
      setSearchParams({}, { replace: true });
      setError(t("coding:workspaceFromLinkNotFound"));
      return;
    }
    const { workspaceId, newSession } = pending;
    deepLinkRef.current = null;
    setSearchParams({}, { replace: true });
    setSelectedWorkspaceId(workspaceId);
    if (newSession) {
      void startNewChat(workspaceId);
      return;
    }
    const match = filterThreadsForBuildSidebar(threads).find(
      (t) =>
        t.workspaceId === workspaceId &&
        (t.messageCount ?? t.messages.length) > 0
    );
    if (match) void selectCodingSession(match.id);
  }, [workspaces, hydrated, threads, searchParams, setSearchParams, startNewChat, selectCodingSession]);

  const persistWorkspaceToThread = useCallback(
    (wsId: string | null) => {
      if (!wsId) {
        setSelectedWorkspaceId(null);
        return;
      }
      const thread = threads.find((x) => x.id === activeThreadId);
      const msgCount = thread?.messageCount ?? thread?.messages.length ?? 0;
      const prevWs = typeof thread?.workspaceId === "string" ? thread.workspaceId : null;
      if (shouldIsolateWorkspaceThread(msgCount, prevWs, wsId)) {
        void startNewChat(wsId);
        return;
      }
      setSelectedWorkspaceId(wsId);
      if (!activeThreadId) return;
      const aid = sessionMode === "plan" ? "coding_plan" : "coding";
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === activeThreadId
            ? { ...t, workspaceId: wsId, agentId: aid, updatedAt: Date.now() }
            : t
        );
        const th = next.find((x) => x.id === activeThreadId);
        if (th) void putConversation(auth, th).catch(() => {});
        return next;
      });
    },
    [activeThreadId, auth, sessionMode, startNewChat, threads, workspaces]
  );

  const workspaceNameById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const ws of workspaces) {
      if (ws.id && ws.name) m[ws.id] = ws.name;
    }
    return m;
  }, [workspaces]);

  const sidebarThreads = useMemo(() => {
    const visible = threadsVisibleInSidebar(threads, activeThreadId);
    return filterThreadsForBuildSidebar(visible);
  }, [threads, activeThreadId]);

  const buildSidebarGroups = useMemo(
    () => buildBuildSidebarGroups(sidebarThreads, workspaceNameById),
    [sidebarThreads, workspaceNameById]
  );

  const activeToolBucket = sessionMode === "plan" ? CODING_PLAN_TOOL_NAMES : CODING_TOOLS;
  const codingToolCount = useMemo(() => {
    const disabled = getDisabledToolNames();
    const bucket = sessionMode === "plan" ? CODING_PLAN_TOOL_NAMES : CODING_TOOLS;
    return bucket.filter((x) => !disabled.includes(x)).length;
  }, [sessionMode]);

  useEffect(() => {
    if (hydrated && userId && !isAdminUser) {
      navigate("/chat", { replace: true });
    }
  }, [hydrated, userId, isAdminUser, navigate]);

  if (!hydrated || !userId) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center overflow-hidden text-sm text-surface-muted">
        {t("coding:loadingBuildWorkspace")}
      </div>
    );
  }

  if (!isAdminUser) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center overflow-hidden text-sm text-surface-muted">
        Redirecting to Chat…
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden bg-surface">
      {permAsk ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4 py-8"
          role="dialog"
          aria-modal="true"
          aria-labelledby="perm-ask-title"
        >
          <div className="max-h-[85vh] w-full max-w-lg overflow-hidden rounded-2xl border border-amber-700/40 bg-[#141414] shadow-2xl">
            <div className="border-b border-surface-border px-5 py-4">
              <h2 id="perm-ask-title" className="text-base font-semibold text-white">
                {t("coding:permAskTitle")}
              </h2>
              <p className="mt-1 text-xs text-surface-muted">{t("coding:planBuildPermissionHint")}</p>
            </div>
            <div className="max-h-[50vh] overflow-y-auto px-5 py-3">
              <p className="text-sm font-medium text-amber-200/90">{permAsk.toolName}</p>
              <pre className="mt-2 whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/40 p-3 text-[11px] leading-relaxed text-neutral-300">
                {permAsk.argsPreview || t("coding:permAskNoArgs")}
              </pre>
            </div>
            <div className="flex flex-wrap gap-2 border-t border-surface-border px-5 py-4">
              <button
                type="button"
                className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                onClick={() => {
                  const w = wsRef.current;
                  if (!w || w.readyState !== WebSocket.OPEN) {
                    setPermAsk(null);
                    return;
                  }
                  w.send(JSON.stringify({ type: "permission_reply", request_id: permAsk.requestId, reply: "once" }));
                  setPermAsk(null);
                }}
              >
                Allow once
              </button>
              <button
                type="button"
                className="rounded-lg bg-sky-700 px-3 py-2 text-sm font-medium text-white hover:bg-sky-600"
                onClick={() => {
                  const w = wsRef.current;
                  if (!w || w.readyState !== WebSocket.OPEN) {
                    setPermAsk(null);
                    return;
                  }
                  w.send(JSON.stringify({ type: "permission_reply", request_id: permAsk.requestId, reply: "always" }));
                  setPermAsk(null);
                }}
              >
                Always (this run)
              </button>
              <button
                type="button"
                className="rounded-lg border border-red-800/60 bg-red-950/40 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-950/70"
                onClick={() => {
                  const w = wsRef.current;
                  if (!w || w.readyState !== WebSocket.OPEN) {
                    setPermAsk(null);
                    return;
                  }
                  w.send(JSON.stringify({ type: "permission_reply", request_id: permAsk.requestId, reply: "reject" }));
                  setPermAsk(null);
                }}
              >
                {t("coding:reject")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      <aside className="flex h-full min-h-0 w-[260px] shrink-0 flex-col border-r border-surface-border bg-[#0d0d0d]">
        <div className="shrink-0 border-b border-surface-border p-3">
          <button
            type="button"
            onClick={() => void startNewChat()}
            className="w-full rounded-lg border border-surface-border bg-white/5 px-3 py-2 text-left text-sm text-neutral-200 hover:bg-white/10"
          >
            {t("coding:newBuildSession")}
          </button>
          <p className="mt-2 text-[10px] leading-snug text-surface-muted">
            {t("coding:modeStatus", {
              mode: sessionMode === "plan" ? t("coding:modePlan") : t("coding:modeBuild"),
              enabled: codingToolCount,
              total: activeToolBucket.length,
            })}
          </p>
          <p className="mt-2 text-[10px] leading-snug text-sky-300/80">{t("coding:subagentHint")}</p>
        </div>

        <div className="shrink-0 border-b border-surface-border p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-surface-muted">{t("coding:project")}</p>
            <button
              type="button"
              onClick={() => setShowCreateWorkspace(true)}
              className="text-[10px] text-sky-400 hover:text-sky-300"
            >
              {t("coding:projectNew")}
            </button>
          </div>
          {workspaces.length === 0 ? (
            <p className="mt-2 text-[10px] text-surface-muted">{t("coding:noWorkspacesYet")}</p>
          ) : (
            <select
              className="mt-2 w-full rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-neutral-200"
              value={selectedWorkspaceId ?? ""}
              onChange={(e) => persistWorkspaceToThread(e.target.value || null)}
            >
              {workspaces.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                </option>
              ))}
            </select>
          )}
          {selectedWorkspace && (
            <div className="mt-2 flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-surface-muted truncate flex-1" title={selectedWorkspace.path}>
                  {selectedWorkspace.path}
                </span>
                {(selectedWorkspace.name || "").trim() === "agentlayer-self" ? (
                  <span
                    className="shrink-0 rounded border border-red-500/30 bg-red-500/10 px-1.5 py-0.5 text-[9px] font-medium text-red-200/90"
                    title={t("workspace:selfCopyTitle")}
                  >
                    {t("coding:selfCopyBadge")}
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => void startNewChat(selectedWorkspace.id)}
                  className="shrink-0 text-[10px] text-sky-400 hover:text-sky-300"
                  title={t("workspace:freshCodingSessionTitle")}
                >
                  {t("coding:newSession")}
                </button>
                {(selectedWorkspace.name || "").trim() === "agentlayer-self" ? (
                  <button
                    type="button"
                    onClick={() =>
                      void handleResetSelfWorkspace(selectedWorkspace.id, { backupExisting: true })
                    }
                    className="shrink-0 text-[10px] text-orange-300/80 hover:text-orange-200"
                    title={t("workspace:resetWithBackupTitle")}
                  >
                    {t("coding:reset")}
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => handleDeleteWorkspace(selectedWorkspace.id)}
                  className="shrink-0 text-[10px] text-red-400/70 hover:text-red-300"
                >
                  {t("coding:deleteShort")}
                </button>
              </div>
              <p className="text-[10px] leading-snug text-surface-muted">{t("coding:workspaceSwitchHint")}</p>
              {(selectedWorkspace.name || "").trim() === "agentlayer-self" ? (
                <div className="text-[10px] leading-snug text-surface-muted">
                  {t("coding:selfWorkspaceHint")}
                  <button
                    type="button"
                    onClick={() =>
                      void handleResetSelfWorkspace(selectedWorkspace.id, { backupExisting: false })
                    }
                    className="ml-2 text-[10px] text-red-300/80 hover:text-red-200 underline"
                    title={t("workspace:resetWithoutBackupTitle")}
                  >
                    {t("coding:resetWithoutBackup")}
                  </button>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {showCreateWorkspace && (
          <div className="shrink-0 border-b border-surface-border bg-black/50 p-3">
            <p className="text-xs font-medium text-neutral-200">{t("coding:createWorkspace")}</p>
            <input
              type="text"
              placeholder={t("workspace:workspaceNamePlaceholder")}
              value={newWorkspaceName}
              onChange={(e) => setNewWorkspaceName(e.target.value)}
              className="mt-2 w-full rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-neutral-200 placeholder:text-surface-muted"
            />
            <input
              type="text"
              placeholder={t("workspace:gitUrlOptionalPlaceholder")}
              value={newWorkspaceGitUrl}
              onChange={(e) => setNewWorkspaceGitUrl(e.target.value)}
              className="mt-2 w-full rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-neutral-200 placeholder:text-surface-muted"
            />
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={handleCreateWorkspace}
                disabled={creatingWorkspace || !newWorkspaceName.trim()}
                className="rounded-lg bg-sky-600 px-2 py-1 text-xs text-white hover:bg-sky-500 disabled:opacity-40"
              >
                {creatingWorkspace ? t("coding:creating") : t("coding:create")}
              </button>
              <button
                type="button"
                onClick={() => { setShowCreateWorkspace(false); setNewWorkspaceName(""); setNewWorkspaceGitUrl(""); }}
                className="rounded-lg border border-surface-border px-2 py-1 text-xs text-neutral-400 hover:text-neutral-200"
              >
                {t("coding:cancel")}
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-2 py-2">
          <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-surface-muted">
            {t("coding:buildSessions")}
          </p>
          {buildSidebarGroups.length === 0 ? (
            <p className="px-2 text-[10px] leading-snug text-surface-muted">
              No build sessions yet. Pick a project above and start a new session.
            </p>
          ) : null}
          <div className="flex flex-col gap-3">
            {buildSidebarGroups.map((g) => (
              <section key={g.workspaceId ?? "none"} className="min-w-0">
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
                          onClick={() => void selectCodingSession(t.id)}
                        >
                          <span className="line-clamp-2 min-w-0 flex-1 text-left">{t.title}</span>
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
                            onClick={() => renameThread(t.id)}
                          >
                            Ren
                          </button>
                          <button
                            type="button"
                            className="rounded px-1 text-[10px] text-red-400/90 hover:text-red-300"
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
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-surface-border bg-white/5 text-lg font-semibold text-neutral-300">
              {"</>"}
            </div>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">{t("coding:buildHeroTitle")}</h1>
            <p className="max-w-md text-sm text-surface-muted">{t("coding:buildHeroIntro")}</p>
            <CodingBuildPlanToggle
              mode={sessionMode}
              onChange={handleCodingSessionModeChange}
              helper={
                sessionMode === "plan" ? t("coding:planModeToggleTitle") : t("coding:buildModeToggleTitle")
              }
              className="max-w-md items-start"
            />
            {userId ? (
              <ImplementationBranchSetting
                className="max-w-md"
                value={implBranchPreference}
                onChange={setImplBranchPreference}
              />
            ) : null}
            <button
              type="button"
              onClick={() => void startNewChat()}
              className="rounded-lg border border-surface-border bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15"
            >
              {t("coding:newBuildSessionBtn")}
            </button>
          </div>
        ) : (
          <>
            <div className="shrink-0 border-b border-surface-border px-4 py-3 sm:px-6">
              <p className="mb-2 truncate text-sm font-medium text-white">
                {activeThread?.title ?? t("coding:buildSessionDefaultTitle")}
              </p>
              <div className="grid gap-3 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_17.5rem] lg:items-stretch">
                <div className="min-w-0 space-y-2">
                  <CodingBuildPlanToggle
                    mode={sessionMode}
                    onChange={handleCodingSessionModeChange}
                    helper={
                      sessionMode === "plan"
                        ? t("coding:planModeToggleTitleThread")
                        : t("coding:buildModeThreadHelper")
                    }
                  />
                  {userId ? (
                    <ImplementationBranchSetting
                      value={implBranchPreference}
                      onChange={setImplBranchPreference}
                    />
                  ) : null}
                </div>
                <AgentActivityPanel
                  entries={activityEntries}
                  loading={activityLoading}
                  emptyHint={t("coding:activityEmptyHint")}
                  layout="header"
                  className="min-h-0 w-full"
                  showSubagentToggle
                  showSubagents={showSubagentsInActivity}
                  onShowSubagentsChange={(on) => {
                    setShowSubagentsInActivity(on);
                    persistShowSubagentsPref(userId, on);
                  }}
                />
                <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-surface-border lg:pl-4">
                  <SessionRuntimeBar
                    runtime={sessionRuntime}
                    usage={tokenUsage}
                    className="w-full"
                    mcpAddon={
                      selectedWorkspaceId && selectedWorkspace && selectedWorkspace.access_role !== "viewer" ? (
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
                  {selectedWorkspace ? (
                    <WorkspaceRetrievalBar
                      auth={auth}
                      workspace={selectedWorkspace}
                      canEdit={selectedWorkspace.access_role !== "viewer"}
                      onWorkspaceUpdated={(ws) => {
                        setWorkspaces((prev) => prev.map((w) => (w.id === ws.id ? ws : w)));
                      }}
                      className="w-full"
                    />
                  ) : null}
                  <div className="w-full">
                    <label className="flex cursor-pointer items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                      <input
                        type="checkbox"
                        className="rounded border-surface-border bg-[#1a1a1a] text-sky-500"
                        checked={agentStreamLlmUi}
                        onChange={(e) => {
                          const on = e.target.checked;
                          setAgentStreamLlm(on);
                          setAgentStreamLlmUi(on);
                        }}
                        title={t("coding:streamLlmTokensTitle")}
                      />
                      <span>{t("coding:llmStreamLabel")}</span>
                    </label>
                  </div>
                  <div className="w-full">
                    <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                      {t("coding:modelLabel")}
                    </label>
                    <select
                      className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                      value={modelSelectValue || defaultSelectValue}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={!modelsCatalogReady || modelRows.length === 0}
                    >
                      {!modelsCatalogReady ? (
                        <option value="">{t("coding:loadingModels")}</option>
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
                  <div className="w-full">
                    <label className="block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                      {t("coding:embeddingLabel")}
                    </label>
                    <select
                      className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                      value={embeddingModel || embeddingModelRows[0] || ""}
                      onChange={(e) => void setEmbeddingModelSelection(e.target.value)}
                      disabled={
                        !modelsCatalogReady ||
                        embeddingModelSaving ||
                        !embeddingMeta?.configured ||
                        (embeddingModelRows.length === 0 && !embeddingModel) ||
                        !isAdminUser
                      }
                      title={
                        !isAdminUser
                          ? t("coding:embeddingAdminOnlyTitle")
                          : t("coding:embeddingModelTitle")
                      }
                    >
                      {!modelsCatalogReady ? (
                        <option value="">{t("coding:embeddingLoading")}</option>
                      ) : embeddingModelRows.length === 0 ? (
                        <option value={embeddingModel || ""}>
                          {embeddingModel || t("coding:embeddingNoModels")}
                        </option>
                      ) : (
                        embeddingModelRows.map((id) => (
                          <option key={id} value={id}>
                            {id}
                          </option>
                        ))
                      )}
                    </select>
                    {embeddingStatusHint ? (
                      <p
                        className={`mt-1 text-[10px] leading-snug ${
                          embeddingMeta?.reachable === false ? "text-amber-300/95" : "text-neutral-500"
                        }`}
                      >
                        {embeddingStatusHint}
                      </p>
                    ) : null}
                    {!isAdminUser && embeddingMeta?.configured ? (
                      <p className="mt-0.5 text-[10px] text-neutral-500">
                        {t("coding:embeddingChangeAdminHint")}
                      </p>
                    ) : null}
                  </div>
                  {modelsCatalogReady && modelRows.length === 0 ? (
                    <p className="w-full text-[10px] leading-snug text-neutral-500">
                      {t("coding:chatProviderAdminHint")}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>

            {error ? (
              <div className="shrink-0 border-b border-red-900/50 bg-red-950/40 px-6 py-2 text-sm text-red-300">
                {error}
              </div>
            ) : null}

            <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
              <CodingWorkspacePanels
                auth={auth}
                workspaceId={selectedWorkspaceId}
                changesRefreshKey={changesRefreshKey}
              />

              <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                {userTurns.length > 0 ? (
                  <TurnNavigatorHorizontal
                    userTurns={userTurns}
                    activeId={selectedTurnId}
                    onSelect={handleSelectTurn}
                    className="shrink-0 border-b border-surface-border px-4 py-2"
                  />
                ) : null}
                <div className="flex min-h-0 flex-1 overflow-hidden">
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
                    className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 lg:px-6 lg:py-6"
                  >
                  {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <div className="flex h-14 w-14 items-center justify-center rounded-full border border-surface-border bg-white/5 text-lg font-semibold text-neutral-300">
                        {"</>"}
                      </div>
                      <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">
                        Hello, {displayName}
                      </h1>
                      <p className="mt-2 max-w-md text-sm text-surface-muted">
                        What would you like to build or fix?
                      </p>
                    </div>
                  ) : (
                    <ul className="mx-auto flex w-full max-w-3xl flex-col gap-3">
                      {messages.filter(chatMessageHasVisibleContent).map((m, i) => {
                        const proposals = m.role === "assistant" ? extractProposals(m.content) : [];
                        return (
                          <li
                            key={m.id ?? `${i}-${m.role}-${m.content.slice(0, 24)}`}
                            id={m.role === "user" && m.id ? `msg-${m.id}` : undefined}
                            className={`flex w-full scroll-mt-4 ${m.role === "user" ? "justify-start" : "justify-end"}`}
                          >
                            <div
                              className={`max-w-[min(100%,42rem)] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                                m.role === "user"
                                  ? "border border-sky-900/40 bg-[#1a2a3d] text-neutral-100"
                                  : "border border-white/10 bg-[#1e1e1e] text-neutral-200"
                              }`}
                            >
                              <span className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                                {m.role === "user" ? "You" : "Agent"}
                              </span>
                              {m.role === "user" ? (
                                <MessageBody content={m.content} />
                              ) : proposals.length > 0 ? (
                                <div className="space-y-2">
                                  <div className="whitespace-pre-wrap">
                                    {stripProposalBlocks(m.content)}
                                  </div>
                                  {proposals.map((p) => (
                                    <ProposalCard
                                      key={p.id}
                                      proposal={p}
                                      selected={
                                        selectedOptions.get(p.id)?.option.id ?? null
                                      }
                                      onSelect={(opt) => handleSelectOption(p, opt)}
                                    />
                                  ))}
                                </div>
                              ) : (
                                <div className="whitespace-pre-wrap">{m.content}</div>
                              )}
                            </div>
                          </li>
                        );
                      })}
                      {showAgentRunningPlaceholder ? (
                        <li className="flex w-full justify-end">
                          <div className="max-w-[min(100%,42rem)] rounded-2xl border border-sky-900/50 bg-sky-950/25 px-4 py-3 text-sm text-sky-100/90 shadow-sm">
                            <span className="mb-1 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-sky-300/80">
                              <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-sky-400" />
                              Agent
                            </span>
                            <p className="text-neutral-300">
                              {sessionMode === "plan"
                                ? t("coding:planAgentRunning")
                                : t("coding:codingAgentRunning")}
                            </p>
                          </div>
                        </li>
                      ) : null}
                    </ul>
                  )}
                  <div ref={messagesEndRef} className="h-px w-full shrink-0" aria-hidden />
                  </div>
                </div>

                <div className="shrink-0 border-t border-surface-border bg-[#0c0c0c] px-4 py-3 lg:px-6 lg:py-4">
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
                <div className="rounded-2xl border border-surface-border bg-[#141414] p-3 shadow-xl">
                  <textarea
                    className="min-h-[52px] w-full resize-none bg-transparent text-sm text-neutral-100 placeholder:text-neutral-500 focus:outline-none"
                    placeholder={t("coding:composerPlaceholder")}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    rows={2}
                    disabled={loading}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (draft.trim() && !loading && selectedWorkspaceId) onSend();
                      }
                    }}
                  />
                  <div className="mt-2 flex items-center justify-end gap-2">
                    {loading ? (
                      <button
                        type="button"
                        className="rounded-lg border border-amber-500/60 bg-amber-950/50 px-4 py-2 text-sm font-medium text-amber-100 hover:bg-amber-900/40"
                        onClick={() => onCancelInFlight()}
                      >
                        {t("coding:cancel")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={!draft.trim() || !selectedWorkspaceId}
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
                      Suggestions
                    </p>
                    <ul className="flex flex-col gap-2">
                      {codingSuggested.map((s) => (
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
              const ws = await fetchWorkspaces(auth);
              setWorkspaces(ws);
              setSessionRuntime(await fetchSessionRuntime(auth, selectedWorkspaceId));
            } catch {
              /* ignore */
            }
          }}
        />
      ) : null}
    </div>
  );
}
