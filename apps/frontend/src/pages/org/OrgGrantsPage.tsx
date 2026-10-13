import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { hasOrgSurface } from "../../auth/deploymentMode";
import { Badge } from "../../ui/Badge";
import { fetchWorkspacesApi } from "../../lib/workspacesApi";
import {
  fetchEntityGrantsApi,
  grantsForLevel,
  memberAccessLevel,
  replaceEntityGrantsApi,
  type GrantAccessLevel,
} from "../../lib/entityGrantsApi";
import { Select } from "../../ui/Field";
import { Button } from "../../ui/Button";
import { Table, type TableColumn } from "../../ui/Table";

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

  // The two narrow tracks get fixed widths on purpose: the status column carries
  // either "Up to date" or a backend error message, and with auto layout the
  // first failing workspace would re-track the name and select columns under it.
  const columns: Array<TableColumn<Row>> = [
    {
      key: "workspace",
      header: t("org:grantsColWorkspace"),
      render: (row) => (
        <>
          <span className="font-medium text-ink-primary">{row.name}</span>
          {row.visibility !== "tenant" ? (
            <Badge tone="warning" className="ml-base">
              {t("org:grantsPrivateTag")}
            </Badge>
          ) : null}
        </>
      ),
    },
    {
      key: "access",
      header: t("org:grantsColMemberAccess"),
      width: "12rem",
      // The row's own label stays: every column header reads the same on every
      // row, so without it a screen reader cannot say which workspace a level is for.
      render: (row) => (
        <>
          <label className="sr-only" htmlFor={`grant-${row.id}`}>
            {t("org:grantsColMemberAccess")} — {row.name}
          </label>
          <Select
            id={`grant-${row.id}`}
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
          </Select>
        </>
      ),
    },
    {
      key: "status",
      header: t("org:grantsColStatus"),
      width: "14rem",
      render: (row) =>
        row.saving ? (
          <span className="text-ink-muted">{t("org:grantsSaving")}</span>
        ) : row.error ? (
          <span className="text-danger">{row.error}</span>
        ) : row.visibility !== "tenant" ? (
          <span className="text-badge-warning">{t("org:grantsInertWhilePrivate")}</span>
        ) : (
          <span className="text-ink-muted">{t("org:grantsUpToDate")}</span>
        ),
    },
  ];

  if (!hasOrgSurface(auth.user)) {
    return (
      <div className="mx-auto max-w-pageNarrow px-wide py-page text-sm text-ink-muted">
        {t("org:grantsNoOrg")}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-pageWide px-wide py-deep sm:px-broad">
      <h1 className="text-2xl font-semibold text-ink-primary">{t("org:grantsTitle")}</h1>
      <p className="mt-base max-w-measure text-sm text-ink-muted">{t("org:grantsIntro")}</p>

      <div className="mt-wide rounded-card border border-line bg-card px-wide py-soft text-xs text-ink-muted">
        {t("org:grantsImplicitAdmins")}
      </div>

      <div className="mt-broad flex flex-wrap items-center gap-soft">
        <Button
          size="lg"
          type="button"
          className="bg-white/10 px-wide py-snug text-xs hover:bg-white/15"
          disabled={loading}
          onClick={() => void load()}
        >
          {t("org:grantsRefresh")}
        </Button>
      </div>

      {message ? <p className="mt-wide text-sm text-badge-success">{message}</p> : null}
      {error ? <p className="mt-wide text-sm text-danger">{error}</p> : null}

      {/* One table for both the loading and the loaded shape: the header, the
          row rhythm and the empty row are all in place before the fan-out
          resolves, so nothing below it moves when the grants land.
          52 px is a real row here — `py-base` (8+8) around the tallest cell
          content, the 36 px `Select` (`py-snug` 6+6 + 22 px `text-body` + border). */}
      <Table
        className="mt-broad"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        loading={loading}
        empty={t("org:grantsEmpty")}
        rowHeight={52}
      />

      {!loading && privateCount > 0 ? (
        <p className="mt-wide text-xs text-badge-warning">{t("org:grantsPrivateWarning")}</p>
      ) : null}
    </div>
  );
}
