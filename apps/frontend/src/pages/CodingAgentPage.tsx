import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  type AgentTimelineEntry,
  type ChatThread,
  type UiMessage,
} from "../features/chat/chatThreadStorage";
import {
  createConversation,
  deleteConversationApi,
  fetchConversationDetail,
  fetchConversationList,
  mapListItemToThread,
  putConversation,
} from "../features/chat/conversationsApi";
import {
  buildUserMessageContent,
  parseContentParts,
  toApiContent,
} from "../features/chat/messageFormat";
import { getDisabledToolNames } from "../features/settings/toolPrefs";
import { buildSidebarGroups } from "../features/chat/groupThreadsForSidebar";
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
import {
  catalogOwnedByForModel,
  fetchModelCatalog,
  formatModelCatalogHint,
  catalogModelOptionUnreachableTitle,
  isCatalogModelOptionDisabled,
  modelOptionLabel,
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
    throw new Error(err.detail ?? "Failed to create workspace");
  }
  const j = (await r.json()) as { workspace: WorkspaceApiRecord };
  return j.workspace;
}

async function deleteWorkspace(auth: ReturnType<typeof useAuth>, workspaceId: string) {
  const r = await apiFetch(`/v1/workspaces/${workspaceId}`, auth, { method: "DELETE" });
  if (!r.ok) {
    const err = (await r.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? "Failed to delete workspace");
  }
  return true;
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
    throw new Error("Branch creation returned no branch name");
  }
  return { branch: j.branch, base_branch: j.base_branch, head_summary: j.head_summary };
}

const CODING_SUGGESTED = [
  "Explain the structure of this project",
  "Find and fix all linting errors",
  "Add unit tests for the main module",
  "Refactor this function to be more readable",
];

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
  if (text.trim()) return text;
  const tcs = msg0?.tool_calls;
  if (Array.isArray(tcs) && tcs.length > 0) {
    return (
      "(No assistant text in the final response — only tool_calls. " +
      "See **Agent activity** for tool runs, or retry if the model should have answered in prose.)"
    );
  }
  return "";
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
  return (
    <div className={`mt-2 flex flex-col gap-1 text-left ${className}`}>
      <label
        className="text-[10px] font-medium uppercase tracking-wide text-surface-muted"
        htmlFor="impl-branch-pref"
      >
        Plan → Build: implementation branch
      </label>
      <select
        id="impl-branch-pref"
        className="max-w-xs rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-neutral-200"
        value={value}
        onChange={(e) => onChange(e.target.value as ImplBranchPreference)}
      >
        <option value="ask">Ask each time</option>
        <option value="always">Always create agent/impl-…</option>
        <option value="never">Never (switch mode only)</option>
      </select>
      <p className="text-[10px] leading-snug text-surface-muted">
        When switching from Plan to Build and this session already has messages. Saved per account in this browser.
      </p>
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
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">Mode</span>
        <div className="inline-flex rounded-lg border border-surface-border bg-black/40 p-0.5">
          <button
            type="button"
            onClick={() => onChange("build")}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "build" ? "bg-sky-600 text-white shadow" : "text-surface-muted hover:text-white"
            }`}
          >
            Build
          </button>
          <button
            type="button"
            onClick={() => onChange("plan")}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              mode === "plan" ? "bg-amber-600 text-white shadow" : "text-surface-muted hover:text-white"
            }`}
          >
            Plan
          </button>
        </div>
      </div>
      {helper ? <p className="text-[10px] leading-snug text-surface-muted">{helper}</p> : null}
    </div>
  );
}

export function CodingAgentPage() {
  const auth = useAuth();
  const { accessToken, user } = auth;
  const userId = user?.id ?? "";

  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelRows, setModelRows] = useState<ModelRow[]>([]);
  const [modelsCatalogReady, setModelsCatalogReady] = useState(false);
  const [modelsCatalogHint, setModelsCatalogHint] = useState<string | null>(null);
  const [modelCatalogAgentlayer, setModelCatalogAgentlayer] = useState<ModelCatalogAgentlayer | null>(null);
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
  const [permAsk, setPermAsk] = useState<PermAskGate | null>(null);
  const [implBranchPreference, setImplBranchPreferenceState] = useState<ImplBranchPreference>("ask");
  const [sessionRuntime, setSessionRuntime] = useState<SessionRuntimePayload | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsageTotals>(() => emptyTokenUsage());
  const [showWorkspaceMcpModal, setShowWorkspaceMcpModal] = useState(false);

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
    },
    [userId, activeThreadId]
  );

  const wsRef = useRef<WebSocket | null>(null);
  const agentHandlerRef = useRef<(ev: MessageEvent) => void>(() => {});
  const activeThreadIdRef = useRef<string | null>(null);
  /** Prepended to the next user message after Plan→Build + server implementation-branch creation. */
  const implementationBranchPreambleRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const toolStartTimesRef = useRef<Map<string, number>>(new Map());
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

  const messages = activeThread?.messages ?? [];
  const agentLog: AgentTimelineEntry[] = activeThread?.agentLog ?? [];
  const models = useMemo(() => modelRows.map((r) => r.id), [modelRows]);
  const defaultModel = models[0] ?? "";

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
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!accessToken || !userId) return;
    let cancelled = false;
    void (async () => {
      try {
        const ws = await fetchWorkspaces(auth);
        if (cancelled) return;
        setWorkspaces(ws);
        if (ws.length > 0 && !selectedWorkspaceId) {
          setSelectedWorkspaceId(ws[0].id);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => { cancelled = true; };
  }, [accessToken, userId, auth, selectedWorkspaceId]);

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
        const withMsgs = mapped.find((x) => (x.messageCount ?? x.messages.length) > 0);
        const pick = withMsgs?.id ?? mapped[0]?.id ?? null;
        if (!pick) { setActiveThreadId(null); setHydrated(true); return; }
        setActiveThreadId(pick);
        const full = await fetchConversationDetail(auth, pick);
        if (cancelled) return;
        setThreads((prev) => prev.map((th) => (th.id === full.id ? full : th)));
        setHydrated(true);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load chats");
          setHydrated(true);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [accessToken, userId, auth]);

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

  const handleCodingSessionModeChange = useCallback(
    async (m: CodingSessionMode) => {
      if (
        m === "build" &&
        sessionMode === "plan" &&
        activeThreadId &&
        selectedWorkspaceId
      ) {
        const t = threads.find((x) => x.id === activeThreadId);
        const hasTranscript = (t?.messages.length ?? 0) > 0;
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
              "Switch to **Build**: create an implementation git branch `agent/impl-…` on the server?\n\n" +
                `Base: **${baseHint}** (workspace default branch; override via PATCH /v1/workspaces if needed).\n\n` +
                "OK = create branch and switch to Build\n" +
                "Cancel = switch to Build without creating a branch"
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
                "Could not create the implementation branch (see error banner). Switch to Build anyway?"
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
      if (!tok) { reject(new Error("Not signed in")); return; }
      const existing = wsRef.current;
      if (existing?.readyState === WebSocket.OPEN) { resolve(existing); return; }
      if (existing) { existing.close(); wsRef.current = null; }
      const ws = new WebSocket(wsUrl(tok));
      ws.onopen = () => { wsRef.current = ws; ws.onmessage = (ev) => agentHandlerRef.current(ev); resolve(ws); };
      ws.onerror = () => reject(new Error("WebSocket connection failed"));
      ws.onclose = () => { if (wsRef.current === ws) wsRef.current = null; };
    });
  }, [accessToken]);

  const runAgentWs = useCallback(async () => {
    if (!accessToken || !activeThreadId) return;
    const tid = activeThreadId;
    const t = threads.find((x) => x.id === tid);
    const effectiveModel = (t?.model || defaultModel).trim();
    if (!t || !effectiveModel) return;

    if (!selectedWorkspaceId) {
      setError("Select a workspace before sending (required for Coding and Plan).");
      return;
    }

    const preamble = implementationBranchPreambleRef.current;
    if (preamble) implementationBranchPreambleRef.current = null;
    const userContentRaw = buildUserMessageContent(draft, []);
    const userContent = preamble ? preamble + userContentRaw : userContentRaw;
    if (!userContent) return;

    setError(null);
    setLoading(true);
    setTokenUsage(emptyTokenUsage());
    const firstUser = t.messages.length === 0;
    const nextMessages: UiMessage[] = [...t.messages, { role: "user", content: userContent }];
    const nextTitle = firstUser ? draft.slice(0, 52) : t.title;
    setThreads((prev) =>
      prev.map((th) =>
        th.id === tid
          ? { ...th, messages: nextMessages, agentLog: [], title: nextTitle, model: effectiveModel, updatedAt: Date.now() }
          : th
      )
    );
    setDraft("");

    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      setLoading(false);
      setPermAsk(null);
      const id = activeThreadIdRef.current;
      if (id) {
        setThreads((prev) => {
          const th = prev.find((x) => x.id === id);
          if (th) void putConversation(auth, th).catch(() => {});
          return prev;
        });
      }
    };

    agentHandlerRef.current = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        const typ = msg.type;
        if (typ === "pong") return;
        if (typ === "error") { setError(typeof msg.detail === "string" ? msg.detail : "Agent error"); finish(); return; }
        if (typ === "chat.completion") {
          if (msg.error) { setError(typeof msg.detail === "string" ? msg.detail : "Cancelled or failed"); finish(); return; }
          const data = msg.data;
          if (data && typeof data === "object" && "usage" in data) {
            setTokenUsage((prev) => addUsageTotals(prev, (data as { usage?: unknown }).usage));
          }
          const content = assistantFromCompletion(data);
          const id = activeThreadIdRef.current;
          if (id && content) {
            setThreads((prev) => {
              const next = prev.map((th) => {
                if (th.id !== id) return th;
                const updated: ChatThread = {
                  ...th,
                  messages: [...th.messages, { role: "assistant", content }],
                  messageCount: th.messages.length + 1,
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
          return;
        }
        if (typ === "agent.permission_ask") {
          const requestId = String(msg.request_id ?? "");
          const toolName = String(msg.tool_name ?? "tool");
          const argsPreview = String(msg.args_preview ?? "");
          if (requestId) {
            setPermAsk({ requestId, toolName, argsPreview });
            appendAgentLine("permission", `Waiting for approval: ${toolName}`);
          }
          return;
        }
        if (typ === "agent.llm_round_start") {
          appendAgentLine("llm", msg.round != null ? `round ${msg.round} (start)` : "round (start)");
          return;
        }
        if (typ === "agent.llm_round") {
          appendAgentLine("llm", msg.round != null ? `round ${msg.round}` : "round");
          if (msg.usage != null) {
            setTokenUsage((prev) => addUsageTotals(prev, msg.usage));
          }
          return;
        }
        if (typ === "agent.tool_start") {
          const toolName = String(msg.name ?? "tool");
          toolStartTimesRef.current.set(toolName, Date.now());
          appendAgentLine("tool_start", `→ ${toolName}`);
          return;
        }
        if (typ === "agent.tool_done") {
          const n = msg.name != null ? String(msg.name) : "tool";
          const ch = msg.result_chars != null ? String(msg.result_chars) : "";
          const durationMs = msg.duration_ms != null ? Number(msg.duration_ms) : null;
          let durationText = "";
          if (durationMs != null && durationMs >= 0) {
            if (durationMs < 1000) durationText = `${durationMs}ms`;
            else if (durationMs < 60000) durationText = `${(durationMs / 1000).toFixed(1)}s`;
            else durationText = `${(durationMs / 60000).toFixed(1)}m`;
          } else {
            const startTime = toolStartTimesRef.current.get(n);
            if (startTime != null) {
              const ms = Date.now() - startTime;
              toolStartTimesRef.current.delete(n);
              if (ms < 1000) durationText = `${ms}ms`;
              else if (ms < 60000) durationText = `${(ms / 1000).toFixed(1)}s`;
              else durationText = `${(ms / 60000).toFixed(1)}m`;
            }
          }
          const parts: string[] = [];
          if (ch) parts.push(`${ch} chars`);
          if (durationText) parts.push(durationText);
          appendAgentLine("tool_done", `${n}${parts.length ? ` (${parts.join(", ")})` : ""}`);
          return;
        }
        if (typ === "agent.done" || typ === "agent.aborted" || typ === "agent.cancelled") {
          appendAgentLine(typ, String(msg.detail ?? ""));
          finish();
          return;
        }
      } catch { setError("Invalid WebSocket message"); finish(); }
    };

    try {
      const ws = await ensureAgentWs();
      const disabledTools = getDisabledToolNames();
      const toolBucket = sessionMode === "plan" ? CODING_PLAN_TOOL_NAMES : CODING_TOOLS;
      const enabledTools = toolBucket.filter((x) => !disabledTools.includes(x));
      const catOb = catalogOwnedByForModel(modelRows, effectiveModel);
      const agentId = sessionMode === "plan" ? "coding_plan" : "coding";

      ws.send(
        JSON.stringify({
          type: "chat",
          body: {
            model: effectiveModel,
            messages: nextMessages.map((m) => ({ role: m.role, content: toApiContent(m.content) })),
            agent_id: agentId,
            TOOL_DOMAIN: "coding",
            workspace_id: selectedWorkspaceId,
            ...(enabledTools.length < toolBucket.length
              ? { agent_disabled_tools: disabledTools }
              : {}),
            ...(catOb ? { agent_model_catalog_owned_by: catOb } : {}),
            agent_permission_ask: true,
          },
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
    }
  }, [accessToken, activeThreadId, appendAgentLine, auth, defaultModel, draft, ensureAgentWs, modelRows, selectedWorkspaceId, sessionMode, threads]);

  const onSend = () => { void runAgentWs(); };

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

  const startNewChat = async () => {
    try {
      const t = await createConversation(auth, {
        title: "New coding session",
        mode: "agent",
        model: defaultModel,
        messages: [],
        agent_log: [],
      });
      if (userId) {
        localStorage.setItem(codingModeStorageKey(userId, t.id), sessionMode);
      }
      setThreads((prev) => [t, ...prev]);
      setActiveThreadId(t.id);
      setDraft("");
      setError(null);
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  const deleteThread = async (id: string) => {
    if (!confirm("Delete this coding session?")) return;
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
      setError(e instanceof Error ? e.message : "Failed to create workspace");
    } finally {
      setCreatingWorkspace(false);
    }
  };

  const handleDeleteWorkspace = async (wsId: string) => {
    if (!confirm("Delete this workspace and all its files?")) return;
    try {
      await deleteWorkspace(auth, wsId);
      setWorkspaces((prev) => prev.filter((w) => w.id !== wsId));
      if (selectedWorkspaceId === wsId) {
        setSelectedWorkspaceId(workspaces.length > 1 ? workspaces.find((w) => w.id !== wsId)?.id ?? null : null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete workspace");
    }
  };

  const selectedWorkspace = useMemo(
    () => workspaces.find((w) => w.id === selectedWorkspaceId) ?? null,
    [workspaces, selectedWorkspaceId]
  );

  const renameThread = (id: string) => {
    const t = threads.find((x) => x.id === id);
    if (!t) return;
    const next = window.prompt("Session title", t.title);
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed) return;
    setThreads((prev) =>
      prev.map((th) => (th.id === id ? { ...th, title: trimmed, updatedAt: Date.now() } : th))
    );
    void putConversation(auth, { ...t, title: trimmed }).catch(() => {});
  };

  const setModel = useCallback(
    (m: string) => {
      if (!activeThreadId) return;
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === activeThreadId ? { ...t, model: m, updatedAt: Date.now() } : t
        );
        const th = next.find((x) => x.id === activeThreadId);
        if (th) void putConversation(auth, th).catch(() => {});
        return next;
      });
    },
    [activeThreadId, auth]
  );

  const sidebarThreads = useMemo(
    () => threads.filter((t) => (t.messageCount ?? t.messages.length) > 0 || t.id === activeThreadId),
    [threads, activeThreadId]
  );

  const sidebarGroups = useMemo(
    () => buildSidebarGroups(sidebarThreads, {}),
    [sidebarThreads]
  );

  const activeToolBucket = sessionMode === "plan" ? CODING_PLAN_TOOL_NAMES : CODING_TOOLS;
  const codingToolCount = useMemo(() => {
    const disabled = getDisabledToolNames();
    const bucket = sessionMode === "plan" ? CODING_PLAN_TOOL_NAMES : CODING_TOOLS;
    return bucket.filter((x) => !disabled.includes(x)).length;
  }, [sessionMode]);

  if (!hydrated || !userId) {
    return (
      <div className="flex h-full min-h-0 flex-1 items-center justify-center overflow-hidden text-sm text-surface-muted">
        Loading coding agent…
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
                Allow tool execution?
              </h2>
              <p className="mt-1 text-xs text-surface-muted">
                Plan or Build may ask before shell and file-changing tools (permission **ask**).
              </p>
            </div>
            <div className="max-h-[50vh] overflow-y-auto px-5 py-3">
              <p className="text-sm font-medium text-amber-200/90">{permAsk.toolName}</p>
              <pre className="mt-2 whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/40 p-3 text-[11px] leading-relaxed text-neutral-300">
                {permAsk.argsPreview || "(no args preview)"}
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
                Reject
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
            + New coding session
          </button>
          <p className="mt-2 text-[10px] leading-snug text-surface-muted">
            Mode:{" "}
            <span className="text-neutral-300">{sessionMode === "plan" ? "Plan (ask on risky tools)" : "Build (full tools)"}</span>
            {" · "}
            {codingToolCount}/{activeToolBucket.length} tools enabled for this mode.
          </p>
          <p className="mt-2 text-[10px] leading-snug text-sky-300/80">
            Optional: ask the model to use{" "}
            <code className="rounded bg-black/40 px-0.5 text-neutral-300">coding_task</code> with{" "}
            <code className="rounded bg-black/40 px-0.5 text-neutral-300">run_plan_subagent: true</code> for a bounded
            embedded read-only planner (no approval UI in that thread); results in{" "}
            <code className="text-neutral-400">assistant_excerpt</code>.
          </p>
        </div>

        <div className="shrink-0 border-b border-surface-border p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-surface-muted">Workspace</p>
            <button
              type="button"
              onClick={() => setShowCreateWorkspace(true)}
              className="text-[10px] text-sky-400 hover:text-sky-300"
            >
              + New
            </button>
          </div>
          {workspaces.length === 0 ? (
            <p className="mt-2 text-[10px] text-surface-muted">No workspaces yet. Create one to start coding.</p>
          ) : (
            <select
              className="mt-2 w-full rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-neutral-200"
              value={selectedWorkspaceId ?? ""}
              onChange={(e) => setSelectedWorkspaceId(e.target.value || null)}
            >
              {workspaces.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                </option>
              ))}
            </select>
          )}
          {selectedWorkspace && (
            <div className="mt-2 flex items-center gap-2">
              <span className="text-[10px] text-surface-muted truncate" title={selectedWorkspace.path}>
                {selectedWorkspace.path}
              </span>
              <button
                type="button"
                onClick={() => handleDeleteWorkspace(selectedWorkspace.id)}
                className="text-[10px] text-red-400/70 hover:text-red-300"
              >
                Del
              </button>
            </div>
          )}
        </div>

        {showCreateWorkspace && (
          <div className="shrink-0 border-b border-surface-border bg-black/50 p-3">
            <p className="text-xs font-medium text-neutral-200">Create Workspace</p>
            <input
              type="text"
              placeholder="Workspace name"
              value={newWorkspaceName}
              onChange={(e) => setNewWorkspaceName(e.target.value)}
              className="mt-2 w-full rounded-lg border border-surface-border bg-black/30 px-2 py-1.5 text-xs text-neutral-200 placeholder:text-surface-muted"
            />
            <input
              type="text"
              placeholder="Git URL (optional)"
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
                {creatingWorkspace ? "Creating..." : "Create"}
              </button>
              <button
                type="button"
                onClick={() => { setShowCreateWorkspace(false); setNewWorkspaceName(""); setNewWorkspaceGitUrl(""); }}
                className="rounded-lg border border-surface-border px-2 py-1 text-xs text-neutral-400 hover:text-neutral-200"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-2 py-2">
          <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-surface-muted">
            Sessions
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
                          onClick={() => setActiveThreadId(t.id)}
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
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">
              Coding Agent
            </h1>
            <p className="max-w-md text-sm text-surface-muted">
              Give coding instructions. The agent reads, writes, and edits files using dashboard-scoped tools.
            </p>
            <CodingBuildPlanToggle
              mode={sessionMode}
              onChange={handleCodingSessionModeChange}
              helper={
                sessionMode === "plan"
                  ? "Plan: same tools as Build; bash/writes may ask in the UI. Choice is saved per session."
                  : "Build: same tool surface; risky tools may ask when enabled."
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
              + New coding session
            </button>
          </div>
        ) : (
          <>
            <div className="shrink-0 border-b border-surface-border px-4 py-3 sm:px-6">
              <p className="mb-2 truncate text-sm font-medium text-white">
                {activeThread?.title ?? "Coding session"}
              </p>
              <div className="grid gap-3 lg:grid-cols-[1fr,17.5rem] lg:items-start">
                <div className="min-w-0 space-y-2">
                  <CodingBuildPlanToggle
                    mode={sessionMode}
                    onChange={handleCodingSessionModeChange}
                    helper={
                      sessionMode === "plan"
                        ? "Plan: same tools as Build; bash/writes ask in the UI when enabled. Prefer a written handoff before big edits."
                        : "Full coding tools on the selected workspace."
                    }
                  />
                  {userId ? (
                    <ImplementationBranchSetting
                      value={implBranchPreference}
                      onChange={setImplBranchPreference}
                    />
                  ) : null}
                </div>
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
                      Model
                    </label>
                    <select
                      className="mt-0.5 w-full rounded-lg border border-surface-border bg-[#1a1a1a] px-2.5 py-1.5 text-sm text-neutral-100"
                      value={activeThread?.model || defaultModel}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={!modelsCatalogReady || modelRows.length === 0}
                    >
                      {!modelsCatalogReady ? (
                        <option value="">Loading models…</option>
                      ) : modelRows.length === 0 ? (
                        <option value="">{modelsCatalogHint ?? "No models available."}</option>
                      ) : (
                        modelRows.map((row) => {
                          const catalogDown = isCatalogModelOptionDisabled(row, modelCatalogAgentlayer);
                          return (
                            <option
                              key={`${row.owned_by ?? "ollama"}:${row.id}`}
                              value={row.id}
                              disabled={catalogDown}
                              title={catalogDown ? catalogModelOptionUnreachableTitle(row, modelCatalogAgentlayer) : undefined}
                            >
                              {modelOptionLabel(row)}
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

            {error ? (
              <div className="shrink-0 border-b border-red-900/50 bg-red-950/40 px-6 py-2 text-sm text-red-300">
                {error}
              </div>
            ) : null}

            <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
              <CodingWorkspacePanels auth={auth} workspaceId={selectedWorkspaceId} />

              <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 lg:px-6 lg:py-6">
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
                      {messages.map((m, i) => {
                        const proposals = m.role === "assistant" ? extractProposals(m.content) : [];
                        return (
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
                      {loading ? (
                        <li className="flex w-full justify-end">
                          <div className="max-w-[min(100%,42rem)] rounded-2xl border border-sky-900/50 bg-sky-950/25 px-4 py-3 text-sm text-sky-100/90 shadow-sm">
                            <span className="mb-1 flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-sky-300/80">
                              <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-sky-400" />
                              Agent
                            </span>
                            <p className="text-neutral-300">
                              {sessionMode === "plan"
                                ? "Plan agent running (may prompt before edits/shell)…"
                                : "Coding agent running…"}
                            </p>
                          </div>
                        </li>
                      ) : null}
                    </ul>
                  )}
                  <div ref={messagesEndRef} className="h-px w-full shrink-0" aria-hidden />
                </div>

                <div className="flex max-h-36 min-h-0 shrink-0 flex-col border-t border-surface-border bg-black/25">
                  <div className="shrink-0 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-surface-muted">
                    Agent activity
                  </div>
                  {agentLog.length > 0 ? (
                    <ul className="min-h-0 flex-1 overflow-y-auto px-3 pb-2 text-[11px]">
                      {agentLog.map((e) => (
                        <li
                          key={e.id}
                          className={`mb-1 border-l-2 pl-2 text-neutral-400 ${
                            e.kind === "tool_start"
                              ? "border-sky-500/40"
                              : e.kind === "tool_done"
                              ? "border-emerald-500/40"
                              : e.kind === "llm"
                              ? "border-violet-500/40"
                              : e.kind === "permission"
                              ? "border-amber-500/50"
                              : "border-surface-border"
                          }`}
                        >
                          <span className="text-[9px] text-surface-muted">{e.kind}</span>
                          <div className="whitespace-pre-wrap text-neutral-300">{e.text}</div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="px-3 pb-2 text-[11px] text-surface-muted">No activity yet</p>
                  )}
                </div>

                <div className="shrink-0 border-t border-surface-border bg-[#0c0c0c] px-4 py-3 lg:px-6 lg:py-4">
              <div className="relative mx-auto max-w-3xl">
                <div className="rounded-2xl border border-surface-border bg-[#141414] p-3 shadow-xl">
                  <textarea
                    className="min-h-[52px] w-full resize-none bg-transparent text-sm text-neutral-100 placeholder:text-neutral-500 focus:outline-none"
                    placeholder="Describe what you want to build or fix…"
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
                    <button
                      type="button"
                      disabled={!draft.trim() || loading || !selectedWorkspaceId}
                      className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-40"
                      onClick={() => onSend()}
                    >
                      {loading ? "…" : "Send"}
                    </button>
                  </div>
                </div>

                {messages.length === 0 ? (
                  <div className="mt-6">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-surface-muted">
                      Suggestions
                    </p>
                    <ul className="flex flex-col gap-2">
                      {CODING_SUGGESTED.map((s) => (
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
