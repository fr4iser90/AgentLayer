import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { hasOrgSurface } from "../../auth/deploymentMode";
import { fetchWorkspacesApi } from "../../lib/workspacesApi";
import {
  fetchEntityGrantsApi,
  grantsForLevel,
  memberAccessLevel,
  replaceEntityGrantsApi,
  type GrantAccessLevel,
} from "../../lib/entityGrantsApi";

type Row = {
  id: string;
  name: string;
  ownerUserId: string;
  visibility: "private" | "tenant";
  loaded: boolean;
  level: GrantAccessLevel | null;
  saving: boolean;
  error: string | null;
};

const ACCESS_LEVELS: Array<GrantAccessLevel | null> = [null, "view", "edit", "manage"];

type GrantsAccessKey =
  | "org:grantsAccessNone"
  | "org:grantsAccessView"
  | "org:grantsAccessEdit"
  | "org:grantsAccessManage";

// Typed as the literal union rather than `string` — i18next's typed keys reject a
// widened return even though every value it produces is a real key.
function levelLabelKey(level: GrantAccessLevel | null): GrantsAccessKey {
  if (level === null) return "org:grantsAccessNone";
  if (level === "view") return "org:grantsAccessView";
  if (level === "edit") return "org:grantsAccessEdit";
  return "org:grantsAccessManage";
}

/** Company workspace sharing — what a plain tenant member may do with each
workspace the company publishes.

Only `tenant_member` is editable here. `tenant_admin` and `tenant_owner` hold
`manage` implicitly on a company-visible workspace, so a grant row naming them
would be a no-op and offering one would be a trap. */
export function OrgGrantsPage() {
  const { t } = useTranslation(["org"]);
  const auth = useAuth();
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    // Guard the fetch, not just the render: without an org surface the list
    // would be a request that cannot succeed, and the page would still be
    // showing a spinner on its way to "not available".
    if (!hasOrgSurface(auth.user)) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await fetchWorkspacesApi(auth, "company");
      const workspaces = list.workspaces ?? [];
      const base: Row[] = workspaces.map((w) => ({
        id: w.id,
        name: w.name,
        ownerUserId: w.owner_user_id,
        visibility: w.visibility === "tenant" ? "tenant" : "private",
        loaded: false,
        level: null,
        saving: false,
        error: null,
      }));

      // Grants are per-entity only; there is no bulk read. Company-visible
      // workspaces are few, so the fan-out is bounded and done in parallel
      // rather than serially.
      const settled = await Promise.all(
        base.map(async (row) => {
          try {
            const res = await fetchEntityGrantsApi(auth, "workspace", row.id);
            return { ...row, loaded: true, level: memberAccessLevel(res.grants) };
          } catch (e) {
            return {
              ...row,
              loaded: true,
              error: e instanceof Error ? e.message : String(e),
            };
          }
        })
      );
      setRows(settled);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const setLevel = useCallback(
    async (rowId: string, level: GrantAccessLevel | null) => {
      setRows((prev) =>
        prev.map((r) => (r.id === rowId ? { ...r, saving: true, error: null } : r))
      );
      try {
        await replaceEntityGrantsApi(auth, "workspace", rowId, grantsForLevel(level));
        setRows((prev) =>
          prev.map((r) => (r.id === rowId ? { ...r, level, saving: false } : r))
        );
        setMessage(t("org:grantsSaved", { defaultValue: "Saved" }));
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setRows((prev) =>
          prev.map((r) => (r.id === rowId ? { ...r, saving: false, error: msg } : r))
        );
      }
    },
    [auth, t]
  );

  const privateCount = useMemo(
    () => rows.filter((r) => r.visibility !== "tenant").length,
    [rows]
  );

  if (!hasOrgSurface(auth.user)) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 text-sm text-ink-muted">
        {t("org:grantsNoOrg")}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold text-ink-primary">{t("org:grantsTitle")}</h1>
      <p className="mt-2 max-w-3xl text-sm text-ink-muted">{t("org:grantsIntro")}</p>

      <div className="mt-4 rounded-card border border-line bg-card px-4 py-3 text-xs text-ink-muted">
        {t("org:grantsImplicitAdmins")}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="rounded-tile bg-white/10 px-4 py-1.5 text-xs font-medium text-ink-primary hover:bg-white/15 disabled:opacity-50"
          disabled={loading}
          onClick={() => void load()}
        >
          {t("org:grantsRefresh")}
        </button>
      </div>

      {message ? <p className="mt-4 text-sm text-emerald-300">{message}</p> : null}
      {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}

      {loading ? (
        <p className="mt-6 text-sm text-ink-muted">{t("org:grantsLoading")}</p>
      ) : null}

      {!loading && rows.length === 0 ? (
        <p className="mt-6 text-sm text-ink-muted">{t("org:grantsEmpty")}</p>
      ) : null}

      {!loading && rows.length > 0 ? (
        <table className="mt-6 w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-muted">
              <th className="py-2 pr-4 font-medium">{t("org:grantsColWorkspace")}</th>
              <th className="py-2 pr-4 font-medium">{t("org:grantsColMemberAccess")}</th>
              <th className="py-2 font-medium">{t("org:grantsColStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-line/60 align-top">
                <td className="py-3 pr-4">
                  <span className="font-medium text-ink-primary">{row.name}</span>
                  {row.visibility !== "tenant" ? (
                    <span className="ml-2 rounded-tile bg-amber-950/50 px-1.5 py-0.5 text-meta text-amber-300">
                      {t("org:grantsPrivateTag")}
                    </span>
                  ) : null}
                </td>
                <td className="py-3 pr-4">
                  <label className="sr-only" htmlFor={`grant-${row.id}`}>
                    {t("org:grantsColMemberAccess")} — {row.name}
                  </label>
                  <select
                    id={`grant-${row.id}`}
                    className="rounded-tile border border-line bg-field px-2 py-1.5 text-xs text-ink-primary disabled:opacity-50"
                    value={row.level === null ? "" : row.level}
                    disabled={row.saving || row.visibility !== "tenant"}
                    onChange={(e) => {
                      const next = e.target.value === "" ? null : (e.target.value as GrantAccessLevel);
                      void setLevel(row.id, next);
                    }}
                  >
                    {ACCESS_LEVELS.map((lvl) => (
                      <option key={String(lvl)} value={lvl === null ? "" : lvl}>
                        {t(levelLabelKey(lvl))}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-3 text-xs">
                  {row.saving ? (
                    <span className="text-ink-muted">{t("org:grantsSaving")}</span>
                  ) : row.error ? (
                    <span className="text-rose-300">{row.error}</span>
                  ) : row.visibility !== "tenant" ? (
                    <span className="text-amber-300">{t("org:grantsInertWhilePrivate")}</span>
                  ) : (
                    <span className="text-ink-muted">{t("org:grantsUpToDate")}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {!loading && privateCount > 0 ? (
        <p className="mt-4 text-xs text-amber-300/90">{t("org:grantsPrivateWarning")}</p>
      ) : null}
    </div>
  );
}
