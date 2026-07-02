import { FormEvent, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type ContentStatus =
  | "draft"
  | "in_review"
  | "approved"
  | "published"
  | "deprecated"
  | "archived";

type ContentRow = {
  id: string;
  slug: string;
  title: string;
  body_md: string;
  status: ContentStatus;
  version: number;
  disclaimer_level?: string;
  vertical_profile?: string | null;
  updated_at?: string;
  published_at?: string | null;
  approved_at?: string | null;
  approved_by_user_id?: string | null;
  published_by_user_id?: string | null;
  last_review_comment?: string | null;
};

type VersionRow = {
  version: number;
  title: string;
  created_at?: string;
};

type ContentResponse = {
  content?: ContentRow;
  items?: ContentRow[];
  rag?: { chunk_count?: number };
  detail?: string;
};

type VersionsResponse = {
  items?: VersionRow[];
};

function apiBase(deploymentMode: string): string {
  return deploymentMode === "agent_system" ? "/v1/admin/tenant-content" : "/v1/org/tenant-content";
}

function statusBadge(status: string, t: (k: string) => string): string {
  if (status === "published") return t("org:cmsStatusPublished");
  if (status === "archived") return t("org:cmsStatusArchived");
  if (status === "in_review") return t("org:cmsStatusInReview");
  if (status === "approved") return t("org:cmsStatusApproved");
  if (status === "deprecated") return t("org:cmsStatusDeprecated");
  return t("org:cmsStatusDraft");
}

export function OrgContentCms({ onPublished }: { onPublished?: () => void }) {
  const { t } = useTranslation(["org"]);
  const auth = useAuth();
  const deploymentMode = auth.user?.deployment_mode ?? "multi_tenant";
  const canPublish =
    (auth.user?.profession_policy?.can_publish_content ??
      auth.user?.site_role === "site_admin") ||
    auth.user?.role?.toLowerCase() === "admin" ||
    auth.user?.membership_role === "tenant_owner" ||
    auth.user?.membership_role === "tenant_admin";
  const canReview =
    auth.user?.profession_policy?.can_review_content === true ||
    auth.user?.site_role === "site_admin" ||
    auth.user?.role?.toLowerCase() === "admin" ||
    auth.user?.membership_role === "tenant_owner" ||
    auth.user?.membership_role === "tenant_admin";
  const base = apiBase(deploymentMode);

  const [items, setItems] = useState<ContentRow[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ContentRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [bodyMd, setBodyMd] = useState("");
  const [rejectComment, setRejectComment] = useState("");
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [listFilter, setListFilter] = useState<"all" | "review">("all");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const selected = items.find((i) => i.id === selectedId) ?? null;
  const status = selected?.status ?? "draft";
  const readOnly = status === "in_review" || status === "archived";

  const loadItems = useCallback(async () => {
    try {
      const res = await apiFetch(base, auth);
      const data = (await res.json()) as ContentResponse;
      if (res.ok && Array.isArray(data.items)) {
        setItems(data.items);
      }
    } catch {
      /* ignore */
    }
  }, [auth, base]);

  const loadReviewQueue = useCallback(async () => {
    if (!canReview) return;
    try {
      const res = await apiFetch(`${base}/review-queue`, auth);
      const data = (await res.json()) as ContentResponse;
      if (res.ok && Array.isArray(data.items)) {
        setReviewQueue(data.items);
      }
    } catch {
      /* ignore */
    }
  }, [auth, base, canReview]);

  const loadVersions = useCallback(
    async (contentId: string) => {
      try {
        const res = await apiFetch(`${base}/${contentId}/versions`, auth);
        const data = (await res.json()) as VersionsResponse;
        if (res.ok && Array.isArray(data.items)) {
          setVersions(data.items);
        } else {
          setVersions([]);
        }
      } catch {
        setVersions([]);
      }
    },
    [auth, base]
  );

  useEffect(() => {
    void loadItems();
    void loadReviewQueue();
  }, [loadItems, loadReviewQueue]);

  useEffect(() => {
    if (!selected) {
      setTitle("");
      setBodyMd("");
      setVersions([]);
      setRejectComment("");
      return;
    }
    setTitle(selected.title);
    setBodyMd(selected.body_md);
    setErr(null);
    setMsg(null);
    void loadVersions(selected.id);
  }, [selected, loadVersions]);

  function startNew() {
    setSelectedId(null);
    setTitle("");
    setBodyMd("");
    setErr(null);
    setMsg(null);
    setRejectComment("");
    setVersions([]);
  }

  async function saveDraft(e?: FormEvent) {
    e?.preventDefault();
    const trimmed = bodyMd.trim();
    if (!title.trim() || !trimmed) {
      setErr(t("org:cmsFieldsRequired"));
      return;
    }
    if (readOnly) {
      setErr(t("org:cmsReadOnly"));
      return;
    }
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const isNew = !selectedId;
      const res = await apiFetch(isNew ? base : `${base}/${selectedId}`, auth, {
        method: isNew ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), body_md: trimmed }),
      });
      const data = (await res.json()) as ContentResponse;
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("org:cmsSaveFailed"));
        return;
      }
      const row = data.content;
      if (row?.id) {
        setSelectedId(row.id);
      }
      setMsg(t("org:cmsDraftSaved"));
      await loadItems();
      await loadReviewQueue();
    } catch {
      setErr(t("org:cmsSaveFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function submitForReview() {
    let id = selectedId;
    const trimmed = bodyMd.trim();
    if (!title.trim() || !trimmed) {
      setErr(t("org:cmsFieldsRequired"));
      return;
    }
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      if (!id) {
        const createRes = await apiFetch(base, auth, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title.trim(), body_md: trimmed }),
        });
        const created = (await createRes.json()) as ContentResponse;
        if (!createRes.ok || !created.content?.id) {
          setErr(typeof created.detail === "string" ? created.detail : t("org:cmsSubmitFailed"));
          return;
        }
        id = created.content.id;
        setSelectedId(id);
      } else if (status === "draft") {
        const patchRes = await apiFetch(`${base}/${id}`, auth, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title.trim(), body_md: trimmed }),
        });
        const patched = (await patchRes.json()) as ContentResponse;
        if (!patchRes.ok) {
          setErr(typeof patched.detail === "string" ? patched.detail : t("org:cmsSubmitFailed"));
          return;
        }
      }
      const res = await apiFetch(`${base}/${id}/submit-for-review`, auth, { method: "POST" });
      const data = (await res.json()) as ContentResponse;
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("org:cmsSubmitFailed"));
        return;
      }
      setMsg(t("org:cmsSubmittedForReview"));
      await loadItems();
      await loadReviewQueue();
    } catch {
      setErr(t("org:cmsSubmitFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function approveSelected() {
    if (!selectedId) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch(`${base}/${selectedId}/approve`, auth, { method: "POST" });
      const data = (await res.json()) as ContentResponse;
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("org:cmsApproveFailed"));
        return;
      }
      setMsg(t("org:cmsApproved"));
      await loadItems();
      await loadReviewQueue();
    } catch {
      setErr(t("org:cmsApproveFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function rejectSelected() {
    if (!selectedId) return;
    const comment = rejectComment.trim();
    if (!comment) {
      setErr(t("org:cmsRejectCommentRequired"));
      return;
    }
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch(`${base}/${selectedId}/reject`, auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment }),
      });
      const data = (await res.json()) as ContentResponse;
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("org:cmsRejectFailed"));
        return;
      }
      setMsg(t("org:cmsRejected"));
      setRejectComment("");
      await loadItems();
      await loadReviewQueue();
    } catch {
      setErr(t("org:cmsRejectFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function publishSelected() {
    if (!selectedId) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch(`${base}/${selectedId}/publish`, auth, { method: "POST" });
      const data = (await res.json()) as ContentResponse;
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("org:cmsPublishFailed"));
        return;
      }
      setMsg(
        t("org:cmsPublishSuccess", {
          version: data.content?.version ?? 1,
          chunks: data.rag?.chunk_count ?? 0,
        })
      );
      onPublished?.();
      await loadItems();
      await loadReviewQueue();
      if (selectedId) {
        await loadVersions(selectedId);
      }
    } catch {
      setErr(t("org:cmsPublishFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function archiveSelected() {
    if (!selectedId) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch(`${base}/${selectedId}/archive`, auth, { method: "POST" });
      const data = (await res.json()) as ContentResponse;
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("org:cmsArchiveFailed"));
        return;
      }
      setMsg(t("org:cmsArchived"));
      await loadItems();
      await loadReviewQueue();
    } catch {
      setErr(t("org:cmsArchiveFailed"));
    } finally {
      setBusy(false);
    }
  }

  const visibleItems = listFilter === "review" ? reviewQueue : items;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,14rem)_1fr]">
      <aside className="rounded-xl border border-surface-border bg-surface-raised p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-surface-muted">
            {t("org:cmsNotes")}
          </p>
          <button
            type="button"
            className="text-xs text-sky-400 hover:text-sky-300"
            onClick={startNew}
          >
            {t("org:cmsNewNote")}
          </button>
        </div>
        {canReview ? (
          <div className="mt-2 flex gap-1 text-[10px]">
            <button
              type="button"
              className={[
                "rounded px-2 py-1",
                listFilter === "all" ? "bg-white/10 text-white" : "text-surface-muted hover:bg-white/5",
              ].join(" ")}
              onClick={() => setListFilter("all")}
            >
              {t("org:cmsFilterAll")}
            </button>
            <button
              type="button"
              className={[
                "rounded px-2 py-1",
                listFilter === "review" ? "bg-white/10 text-white" : "text-surface-muted hover:bg-white/5",
              ].join(" ")}
              onClick={() => setListFilter("review")}
            >
              {t("org:cmsFilterReview")} ({reviewQueue.length})
            </button>
          </div>
        ) : null}
        <ul className="mt-3 max-h-[28rem] space-y-1 overflow-y-auto">
          {visibleItems.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={[
                  "w-full rounded-md px-2 py-2 text-left text-sm",
                  item.id === selectedId
                    ? "bg-white/10 text-white"
                    : "text-neutral-300 hover:bg-white/5",
                ].join(" ")}
                onClick={() => setSelectedId(item.id)}
              >
                <span className="block truncate font-medium">{item.title}</span>
                <span className="text-[10px] text-surface-muted">
                  {statusBadge(item.status, t)} · v{item.version}
                </span>
              </button>
            </li>
          ))}
          {visibleItems.length === 0 ? (
            <li className="px-2 py-4 text-xs text-surface-muted">{t("org:cmsEmpty")}</li>
          ) : null}
        </ul>
      </aside>

      <form onSubmit={(e) => void saveDraft(e)} className="rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">
          {selectedId ? t("org:cmsEditNote") : t("org:cmsNewNote")}
        </h2>
        <p className="mt-1 text-xs text-surface-muted">{t("org:cmsIntro")}</p>

        {selected ? (
          <p className="mt-2 text-xs text-surface-muted">
            {t("org:cmsStatusLabel")}: {statusBadge(status, t)}
            {selected.last_review_comment ? (
              <span className="mt-1 block text-amber-400/90">
                {t("org:cmsLastReviewComment")}: {selected.last_review_comment}
              </span>
            ) : null}
          </p>
        ) : null}

        <label className="mt-4 block text-xs text-surface-muted" htmlFor="cms-title">
          {t("org:knowledgeTitleLabel")}
        </label>
        <input
          id="cms-title"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white disabled:opacity-60"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          disabled={readOnly}
        />

        <label className="mt-4 block text-xs text-surface-muted" htmlFor="cms-body">
          {t("org:knowledgeTextLabel")}
        </label>
        <textarea
          id="cms-body"
          className="mt-1 min-h-56 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white disabled:opacity-60"
          value={bodyMd}
          onChange={(e) => setBodyMd(e.target.value)}
          required
          disabled={readOnly}
        />

        {status === "in_review" && canReview ? (
          <label className="mt-4 block text-xs text-surface-muted" htmlFor="cms-reject-comment">
            {t("org:cmsRejectCommentLabel")}
          </label>
        ) : null}
        {status === "in_review" && canReview ? (
          <textarea
            id="cms-reject-comment"
            className="mt-1 min-h-20 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={rejectComment}
            onChange={(e) => setRejectComment(e.target.value)}
            placeholder={t("org:cmsRejectCommentPlaceholder")}
          />
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={busy || readOnly}
            className="rounded-md border border-surface-border px-4 py-1.5 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-50"
          >
            {busy ? t("org:cmsSaving") : t("org:cmsSaveDraft")}
          </button>
          {status === "draft" ? (
            <button
              type="button"
              disabled={busy}
              className="rounded-md border border-sky-500/40 px-4 py-1.5 text-sm text-sky-300 hover:bg-sky-500/10 disabled:opacity-50"
              onClick={() => void submitForReview()}
            >
              {t("org:cmsSubmitForReview")}
            </button>
          ) : null}
          {status === "in_review" && canReview ? (
            <>
              <button
                type="button"
                disabled={busy}
                className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                onClick={() => void approveSelected()}
              >
                {t("org:cmsApprove")}
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded-md border border-amber-500/40 px-4 py-1.5 text-sm text-amber-300 hover:bg-amber-500/10 disabled:opacity-50"
                onClick={() => void rejectSelected()}
              >
                {t("org:cmsReject")}
              </button>
            </>
          ) : null}
          {status === "approved" && canPublish ? (
            <button
              type="button"
              disabled={busy}
              className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              onClick={() => void publishSelected()}
            >
              {busy ? t("org:knowledgePublishing") : t("org:cmsPublish")}
            </button>
          ) : null}
          {!canPublish && status === "approved" ? (
            <p className="w-full text-xs text-surface-muted">{t("org:cmsPublishRequiresApprover")}</p>
          ) : null}
          {selected?.status === "published" && canPublish ? (
            <button
              type="button"
              disabled={busy}
              className="rounded-md border border-red-500/40 px-4 py-1.5 text-sm text-red-300 hover:bg-red-500/10 disabled:opacity-50"
              onClick={() => void archiveSelected()}
            >
              {t("org:cmsArchive")}
            </button>
          ) : null}
        </div>

        {versions.length > 0 ? (
          <div className="mt-4 rounded-md border border-surface-border/60 bg-black/10 p-3">
            <p className="text-xs font-medium text-surface-muted">{t("org:cmsVersionHistory")}</p>
            <ul className="mt-2 space-y-1 text-xs text-neutral-300">
              {versions.map((v) => (
                <li key={v.version}>
                  v{v.version} — {v.title}
                  {v.created_at ? ` (${v.created_at.slice(0, 10)})` : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {msg ? <p className="mt-3 text-sm text-emerald-400/90">{msg}</p> : null}
        {err ? <p className="mt-3 text-sm text-red-400/90">{err}</p> : null}
      </form>
    </div>
  );
}
