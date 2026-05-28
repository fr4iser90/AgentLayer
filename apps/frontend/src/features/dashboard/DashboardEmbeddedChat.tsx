import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import {
  applyModelCatalogSelection,
  defaultModelCatalogSelectValue,
  fetchModelCatalog,
  findCatalogRowByModelId,
  formatModelCatalogHint,
  modelCatalogSelectValue,
  modelCatalogSelectValueForThread,
  modelOptionLabel,
  resolveComposerModelRouting,
  type ModelRow,
} from "../../lib/modelCatalog";
import type { ChatThread, UiMessage } from "../chat/chatThreadStorage";
import {
  createConversation,
  fetchConversationDetail,
  fetchConversationList,
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
import { streamOpenAiChatChunks } from "../chat/openaiSseStream";

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

type Msg = { role: "user" | "assistant"; content: string };

/** Which dashboard-scoped conversation to open in this panel. */
function pickDashboardConversationRow(
  list: { id?: unknown; shared?: boolean }[],
  readOnly: boolean
): { id?: unknown; shared?: boolean } {
  if (list.length === 0) return {};
  if (readOnly) {
    const shared = list.find((x) => x.shared === true);
    return shared ?? list[0]!;
  }
  const personal = list.find((x) => x.shared !== true);
  return personal ?? list.find((x) => x.shared === true) ?? list[0]!;
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
};

/**
 * Dashboard assistant: **personal** thread by default (only you). A **shared** team thread is optional:
 * create via API (`POST /v1/user/conversations` with `dashboard_id` + `shared: true`) if all members should see it.
 * Same completion API + `agent_dashboard_context` as the full Chat page.
 */
export function DashboardEmbeddedChat({ dashboardId, dashboardTitle, readOnly = false }: Props) {
  const { t } = useTranslation(["dashboard", "errors"]);
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
  const [noSharedChatYet, setNoSharedChatYet] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [modelBeforeFirstSend, setModelBeforeFirstSend] = useState("");
  const lastModelSelectionRef = useRef("");
  const endRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const models = useMemo(() => modelRows.map((r) => r.id), [modelRows]);

  const payloadBase = useMemo(
    () => ({
      agent_dashboard_context: { dashboard_id: dashboardId },
    }),
    [dashboardId]
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const { rows, agentlayer } = await fetchModelCatalog();
        if (cancelled) return;
        setModelRows(rows);
        setModelsCatalogHint(formatModelCatalogHint(agentlayer));
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

  useEffect(() => {
    if (!accessToken || !dashboardId) {
      setInitLoading(false);
      return;
    }
    let cancelled = false;
    setInitLoading(true);
    setInitErr(null);
    setThread(null);
    setNoSharedChatYet(false);
    void (async () => {
      try {
        const list = await fetchConversationList(auth, { dashboardId });
        if (cancelled) return;
        if (list.length > 0) {
          // Viewers: prefer the shared team thread if present. Editors: prefer personal (private) thread.
          const row = pickDashboardConversationRow(
            list as { id?: unknown; shared?: boolean }[],
            readOnly
          ) as { id?: string };
          const id = String(row.id ?? "");
          if (!id) throw new Error("missing conversation id");
          const full = await fetchConversationDetail(auth, id);
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
  }, [accessToken, auth, readOnly, dashboardId, dashboardTitle]);

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
  }, [messages, open, sendLoading]);

  const defaultSelectValue = useMemo(
    () => defaultModelCatalogSelectValue(modelRows),
    [modelRows]
  );
  const modelSelectValue = useMemo(() => {
    if (thread?.model?.trim()) {
      const fromThread = modelCatalogSelectValueForThread(thread.model, thread.modelProvider);
      if (fromThread.includes(":")) return fromThread;
      const row = findCatalogRowByModelId(modelRows, thread.model, thread.modelProvider);
      if (row) return modelCatalogSelectValue(row);
      return fromThread;
    }
    if (modelBeforeFirstSend.trim()) {
      const row = findCatalogRowByModelId(modelRows, modelBeforeFirstSend);
      if (row) return modelCatalogSelectValue(row);
      return modelBeforeFirstSend.trim();
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

  const send = useCallback(async () => {
    if (readOnly) return;
    const userContent = buildUserMessageContent(draft, pendingAttachments);
    if (!userContent || !accessToken || sendLoading) return;
    const routed = resolveComposerModelRouting(
      modelRows,
      lastModelSelectionRef.current || modelSelectValue || defaultSelectValue,
      (thread?.model || modelBeforeFirstSend || modelRows[0]?.id || "").trim(),
      thread?.modelProvider
    );
    if (!routed) {
      setSendErr(
        t("dashboard:resolveModelProviderFailed")
      );
      return;
    }
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
      const payload = {
        model: mdl,
        messages: nextMessages.map((x) => ({
          role: x.role,
          content: toApiContent(x.content),
        })),
        stream: true,
        agent_plain_completion: true,
        stream_options: { include_usage: true },
        ...payloadBase,
        ...(disabledTools.length ? { agent_disabled_tools: disabledTools } : {}),
        agent_model_catalog_owned_by: provider,
      };
      const res = await apiFetch("/v1/chat/completions", auth, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const errBody = (await res.json()) as { detail?: unknown };
          if (errBody.detail != null) detail = String(errBody.detail);
        } catch {
          /* */
        }
        setSendErr(detail);
        setThread(nextThread);
        setDraft(draftSnap);
        setPendingAttachments(attachSnap);
        setSendLoading(false);
        return;
      }
      const ctype = (res.headers.get("content-type") || "").toLowerCase();
      if (ctype.includes("text/event-stream")) {
        let acc = "";
        const assistantCreatedAt = Date.now();
        try {
          for await (const chunk of streamOpenAiChatChunks(res)) {
            if (chunk.kind === "usage") continue;
            acc += chunk.text;
            setThread({
              ...nextThread,
              messages: [...nextMessages, { role: "assistant", content: acc, createdAt: assistantCreatedAt }],
              updatedAt: Date.now(),
            });
          }
        } catch (streamErr) {
          setSendErr(streamErr instanceof Error ? streamErr.message : String(streamErr));
          setThread(nextThread);
          setDraft(draftSnap);
          setPendingAttachments(attachSnap);
          setSendLoading(false);
          return;
        }
        const withAssistant: ChatThread = {
          ...nextThread,
          messages: [
            ...nextMessages,
            { role: "assistant", content: acc.trim() || "(empty)", createdAt: assistantCreatedAt },
          ],
          updatedAt: Date.now(),
        };
        setThread(withAssistant);
        await putConversation(auth, withAssistant);
      } else {
        const data = await res.json();
        const content = assistantFromCompletion(data);
        const withAssistant: ChatThread = {
          ...nextThread,
          messages: content.trim()
            ? [...nextMessages, { role: "assistant", content, createdAt: Date.now() }]
            : nextMessages,
          updatedAt: Date.now(),
        };
        setThread(withAssistant);
        await putConversation(auth, withAssistant);
      }
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
    modelValue,
    pendingAttachments,
    modelRows,
    payloadBase,
    readOnly,
    sendLoading,
    thread,
    dashboardId,
    dashboardTitle,
  ]);

  const hasComposerPayload =
    draft.trim().length > 0 ||
    pendingAttachments.some((a) => a.kind === "image" || a.kind === "textfile");

  const canSend =
    !readOnly &&
    hasComposerPayload &&
    !sendLoading &&
    !!accessToken &&
    !initLoading &&
    !!modelValue.trim();

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
          <p className="shrink-0 px-3 pt-2 text-[11px] leading-snug text-surface-muted">
            {readOnly
              ? t("dashboard:embeddedChatTeamHint")
              : t("dashboard:embeddedChatPrivateHint")}
          </p>
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
                    disabled={readOnly || sendLoading || !thread}
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
                    disabled={readOnly || sendLoading || !thread}
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
    </div>
  );
}
