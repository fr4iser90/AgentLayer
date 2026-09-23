import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { formatDateTimeLocal } from "../../lib/formatDateTime";
import { ConfirmModal } from "../../components/ConfirmModal";

type SubmissionStatus = "pending" | "approved" | "rejected";
type StatusFilter = SubmissionStatus | "all";

type SubmissionRow = {
  id: string;
  agent_id: string;
  title: string | null;
  description: string | null;
  system_prompt: string | null;
  agent_yaml: Record<string, unknown>;
  target_dir: string;
  risk_level: "low" | "medium" | "high";
  status: SubmissionStatus;
  author_id: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  materialize_error: string | null;
  created_at: string;
  updated_at: string;
};

type SubmissionPreview = SubmissionRow & {
  yaml_text: string;
  tool_warnings: string[];
};

const RISK_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

function riskClassName(risk: string): string {
  if (risk === "high") return "bg-red-900/60 text-red-100";
  if (risk === "medium") return "bg-amber-900/60 text-amber-100";
  return "bg-emerald-900/60 text-emerald-100";
}

function statusClassName(status: string): string {
  if (status === "approved") return "bg-emerald-900/60 text-emerald-100";
  if (status === "rejected") return "bg-red-900/60 text-red-100";
  return "bg-sky-900/60 text-sky-100";
}

function Author({ id }: { id: string }) {
  const short = id.length > 8 ? `${id.slice(0, 6)}…` : id;
  return <span className="font-mono text-meta text-ink-muted" title={id}>{short}</span>;
}

export function AdminAgentSubmissions() {
  // Review risk/status keys are built dynamically, so widen `t` beyond the
  // literal-key autocomplete the hook would otherwise enforce.
  const { t } = useTranslation(["admin"]) as unknown as { t: (key: string) => string };
  const auth = useAuth();
  const [submissions, setSubmissions] = useState<SubmissionRow[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<SubmissionPreview | null>(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [confirm, setConfirm] = useState<{ decision: "approve" | "reject" } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadList = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (statusFilter !== "all") params.set("status", statusFilter);
      const res = await apiFetch(`/v1/admin/agents/submissions?${params}`, auth);
      if (!res.ok) {
        setMsg(t("admin:agentSubmissionsLoadFailed"));
        return;
      }
      const data = (await res.json()) as { submissions?: SubmissionRow[] };
      const list = data.submissions ?? [];
      setSubmissions(list);
      // Functional updater so `selectedId` stays out of this callback's deps —
      // otherwise every selection recreates loadList, the mount effect refires,
      // and the reload's `loading` state blanks the list + detail panel.
      setSelectedId((current) => current ?? (list.length ? list[0].id : null));
    } catch {
      setMsg(t("admin:agentSubmissionsLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [auth, t, statusFilter]);

  const loadPreview = useCallback(
    async (id: string) => {
      try {
        const res = await apiFetch(`/v1/agents/submissions/${encodeURIComponent(id)}`, auth);
        if (!res.ok) {
          setPreview(null);
          return;
        }
        setPreview((await res.json()) as SubmissionPreview);
      } catch {
        setPreview(null);
      }
    },
    [auth],
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    setPreview(null);
    setReviewNotes("");
    if (!selectedId) return;
    void loadPreview(selectedId);
  }, [selectedId, loadPreview]);

  const selected = useMemo(
    () => submissions.find((s) => s.id === selectedId) ?? null,
    [submissions, selectedId],
  );

  const sorted = useMemo(
    () => [...submissions].sort((a, b) => {
      const ra = RISK_ORDER[a.risk_level] ?? 9;
      const rb = RISK_ORDER[b.risk_level] ?? 9;
      return ra - rb;
    }),
    [submissions],
  );

  async function submitReview() {
    if (!selectedId || !confirm) return;
    setBusy(true);
    setConfirm(null);
    setMsg(null);
    try {
      const res = await apiFetch(
        `/v1/admin/agents/submissions/${encodeURIComponent(selectedId)}/review`,
        auth,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision: confirm.decision, review_notes: reviewNotes.trim() || undefined }),
        },
      );
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setReviewNotes("");
      await loadList();
      setSelectedId(selectedId);
      setMsg(t("admin:agentSubmissionsReviewRecorded"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-wide py-deep sm:px-broad">
      <h1 className="text-2xl font-semibold text-ink-primary">{t("admin:agentSubmissionsTitle")}</h1>
      <p className="mt-base max-w-3xl text-sm text-ink-muted">{t("admin:agentSubmissionsIntro")}</p>

      <div className="mt-broad flex flex-wrap items-center gap-soft">
        <label className="flex items-center gap-base text-xs text-ink-muted">
          <span className="sr-only">
            {t("admin:agentSubmissionsFilterLabel")}
          </span>
          <select
            id="agents-submissions-filter"
            className="rounded-tile border border-line bg-field px-base py-snug text-xs text-ink-primary"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          >
            <option value="pending">{t("admin:agentSubmissionsFilterPending")}</option>
            <option value="approved">{t("admin:agentSubmissionsFilterApproved")}</option>
            <option value="rejected">{t("admin:agentSubmissionsFilterRejected")}</option>
            <option value="all">{t("admin:agentSubmissionsFilterAll")}</option>
          </select>
        </label>
        <button
          type="button"
          className="rounded-tile bg-white/10 px-wide py-snug text-xs font-medium text-ink-primary hover:bg-white/15 disabled:opacity-50"
          disabled={loading}
          onClick={() => void loadList()}
        >
          {t("admin:agentSubmissionsRefresh")}
        </button>
      </div>

      {msg ? <p className="mt-wide text-sm text-amber-300">{msg}</p> : null}
      {loading ? <p className="mt-broad text-sm text-ink-muted">{t("admin:agentSubmissionsLoading")}</p> : null}
      {!loading && submissions.length === 0 ? (
        <p className="mt-broad text-sm text-ink-muted">{t("admin:agentSubmissionsNone")}</p>
      ) : null}

      {!loading && submissions.length > 0 ? (
        <div className="mt-broad grid gap-wide lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
          <ul className="space-y-base">
            {sorted.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(s.id)}
                  className={`w-full rounded-sheet border px-soft py-soft text-left transition-colors ${
                    selectedId === s.id
                      ? "border-sky-500/40 bg-sky-950/20"
                      : "border-line bg-card hover:border-line-strong"
                  }`}
                >
                  <div className="flex items-center gap-base">
                    <span className="font-medium text-ink-primary">{s.title || s.agent_id}</span>
                    <span className={`rounded-tile px-snug py-hair text-meta ${riskClassName(s.risk_level)}`}>
                      {t(`admin:agentSubmissionsRisk${s.risk_level.charAt(0).toUpperCase()}${s.risk_level.slice(1)}`)}
                    </span>
                    <span className={`rounded-tile px-snug py-hair text-meta ${statusClassName(s.status)}`}>
                      {t(`admin:agentSubmissionsStatus${s.status.charAt(0).toUpperCase()}${s.status.slice(1)}`)}
                    </span>
                  </div>
                  <p className="mt-tight font-mono text-meta text-ink-muted">({s.agent_id})</p>
                  <div className="mt-tight flex items-center gap-base text-meta text-ink-muted">
                    <Author id={s.author_id} />
                    {s.reviewed_by ? (
                      <span>· {t("admin:agentSubmissionsReviewedBy")}: {s.reviewed_by}</span>
                    ) : null}
                  </div>
                </button>
              </li>
            ))}
          </ul>

          {selected ? (
            <div className="rounded-sheet border border-line bg-card p-wide">
              <div className="flex items-start justify-between gap-soft">
                <div>
                  <h2 className="text-lg font-semibold text-ink-primary">
                    {selected.title || selected.agent_id}
                    <span className="ml-base font-mono text-sm text-ink-muted">({selected.agent_id})</span>
                  </h2>
                  <p className="mt-tight text-xs text-ink-muted">{selected.description || "—"}</p>
                </div>
                <span className={`rounded-tile px-base py-tight text-xs ${statusClassName(selected.status)}`}>
                  {t(`admin:agentSubmissionsStatus${selected.status.charAt(0).toUpperCase()}${selected.status.slice(1)}`)}
                </span>
              </div>

              <dl className="mt-wide grid gap-base text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-ink-muted">{t("admin:agentSubmissionsRisk")}</dt>
                  <dd className="mt-tight">
                    <span className={`rounded-tile px-base py-hair text-xs ${riskClassName(selected.risk_level)}`}>
                      {t(`admin:agentSubmissionsRisk${selected.risk_level.charAt(0).toUpperCase()}${selected.risk_level.slice(1)}`)}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted">{t("admin:agentSubmissionsAuthor")}</dt>
                  <dd className="mt-tight"><Author id={selected.author_id} /></dd>
                </div>
                <div>
                  <dt className="text-ink-muted">{t("admin:agentSubmissionsCreatedAt")}</dt>
                  <dd className="mt-tight text-ink-primary">{formatDateTimeLocal(selected.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-ink-muted">{t("admin:agentSubmissionsTargetDir")}</dt>
                  <dd className="mt-tight font-mono text-ink-primary">{selected.target_dir}</dd>
                </div>
                {selected.review_notes ? (
                  <div className="sm:col-span-2">
                    <dt className="text-ink-muted">{t("admin:agentSubmissionsReviewNotes")}</dt>
                    <dd className="mt-tight text-ink-primary">{selected.review_notes}</dd>
                  </div>
                ) : null}
              </dl>

              <div className="mt-wide">
                <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                  {t("admin:agentSubmissionsSystemPrompt")}
                </p>
                <pre className="mt-tight max-h-40 overflow-auto rounded-tile bg-black/40 p-base text-meta text-ink-secondary whitespace-pre-wrap">
                  {selected.system_prompt || "—"}
                </pre>
              </div>

              <div className="mt-soft">
                <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                  {t("admin:agentSubmissionsYaml")}
                </p>
                {preview ? (
                  <pre className="mt-tight max-h-56 overflow-auto rounded-tile bg-black/40 p-base text-meta text-ink-secondary">
                    {preview.yaml_text}
                  </pre>
                ) : (
                  <p className="mt-tight text-meta text-ink-muted">{t("admin:agentSubmissionsYamlLoading")}</p>
                )}
              </div>

              {preview?.tool_warnings.length ? (
                <div className="mt-soft">
                  <p className="text-meta font-medium uppercase tracking-wide text-ink-muted">
                    {t("admin:agentSubmissionsToolWarnings")}
                  </p>
                  <ul className="mt-tight list-disc space-y-hair pl-wide text-meta text-amber-200">
                    {preview.tool_warnings.map((w) => (
                      <li key={w} className="font-mono">{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {selected.materialize_error ? (
                <div className="mt-soft">
                  <p className="text-meta font-medium uppercase tracking-wide text-red-300/80">
                    {t("admin:agentSubmissionsMaterializeError")}
                  </p>
                  <p className="mt-tight font-mono text-meta text-red-200">{selected.materialize_error}</p>
                </div>
              ) : null}

              {selected.status === "pending" ? (
                <div className="mt-wide border-t border-line pt-wide">
                  <label className="block text-xs text-ink-muted" htmlFor="agents-submissions-notes">
                    {t("admin:agentSubmissionsReviewNotes")}
                  </label>
                  <textarea
                    id="agents-submissions-notes"
                    className="mt-tight min-h-20 w-full rounded-tile border border-line bg-field px-soft py-base text-xs text-ink-primary placeholder:text-neutral-500"
                    value={reviewNotes}
                    onChange={(e) => setReviewNotes(e.target.value)}
                    placeholder={t("admin:agentSubmissionsReviewNotesPlaceholder")}
                  />
                  <div className="mt-soft flex flex-wrap gap-base">
                    <button
                      type="button"
                      className="rounded-tile bg-emerald-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-emerald-500 disabled:opacity-50"
                      onClick={() => setConfirm({ decision: "approve" })}
                    >
                      {t("admin:agentSubmissionsApprove")}
                    </button>
                    <button
                      type="button"
                      className="rounded-tile bg-red-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-red-500 disabled:opacity-50"
                      onClick={() => setConfirm({ decision: "reject" })}
                    >
                      {t("admin:agentSubmissionsReject")}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      <ConfirmModal
        open={confirm !== null}
        title={
          confirm?.decision === "approve"
            ? t("admin:agentSubmissionsConfirmApproveTitle")
            : t("admin:agentSubmissionsConfirmRejectTitle")
        }
        description={
          confirm?.decision === "approve"
            ? t("admin:agentSubmissionsConfirmApproveDesc")
            : t("admin:agentSubmissionsConfirmRejectDesc")
        }
        confirmLabel={
          confirm?.decision === "approve"
            ? t("admin:agentSubmissionsApprove")
            : t("admin:agentSubmissionsReject")
        }
        cancelLabel={t("admin:agentSubmissionsCancel")}
        variant={confirm?.decision === "reject" ? "danger" : "default"}
        busy={busy}
        onConfirm={() => void submitReview()}
        onCancel={() => {
          if (!busy) setConfirm(null);
        }}
      />
    </div>
  );
}
