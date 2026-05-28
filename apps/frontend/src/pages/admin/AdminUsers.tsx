import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type TenantRow = { id: number; name?: string | null };

type UserRow = {
  id: string;
  email: string;
  role: string;
  created_at: string;
  external_sub?: string | null;
  display_name?: string | null;
  tenant_id?: number;
  tenant_name?: string | null;
  discord_user_id?: string | null;
  telegram_user_id?: string | null;
  workspace_quota?: number;
  workspace_self_allowed?: boolean;
};

function rowLabel(r: UserRow): string {
  if (r.email?.trim()) return r.email.trim();
  if (r.display_name?.trim()) return r.display_name.trim();
  if (r.external_sub?.trim()) return r.external_sub.trim();
  return r.id;
}

function tenantLabel(row: TenantRow, tr: (key: string, opts?: { id: number }) => string): string {
  const n = (row.name ?? "").trim();
  return n ? `${n} (${row.id})` : tr("admin:usersTenantDefault", { id: row.id });
}

export function AdminUsers() {
  const { t } = useTranslation(["admin", "settings"]);
  const auth = useAuth();
  const { user } = auth;
  const [rows, setRows] = useState<UserRow[]>([]);
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listErr, setListErr] = useState<string | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<"user" | "admin">("user");
  const [newTenantId, setNewTenantId] = useState("1");
  const [createBusy, setCreateBusy] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [newTenantName, setNewTenantName] = useState("");
  const [tenantCreateBusy, setTenantCreateBusy] = useState(false);
  const [tenantCreateMsg, setTenantCreateMsg] = useState<string | null>(null);

  const loadTenants = useCallback(async () => {
    try {
      const res = await apiFetch("/v1/admin/tenants", auth);
      const data = (await res.json()) as { tenants?: TenantRow[] };
      if (!res.ok) {
        setTenants([]);
        return;
      }
      setTenants(data.tenants ?? []);
    } catch {
      setTenants([]);
    }
  }, [auth]);

  const loadUsers = useCallback(async () => {
    setListLoading(true);
    setListErr(null);
    try {
      const res = await apiFetch("/v1/admin/users", auth);
      const data = (await res.json()) as { users?: UserRow[]; detail?: unknown };
      if (!res.ok) {
        setListErr(typeof data.detail === "string" ? data.detail : t("admin:usersLoadFailed"));
        setRows([]);
        return;
      }
      setRows(data.users ?? []);
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:usersLoadFailed"));
      setRows([]);
    } finally {
      setListLoading(false);
    }
  }, [auth]);

  const reloadAll = useCallback(async () => {
    await Promise.all([loadUsers(), loadTenants()]);
  }, [loadUsers, loadTenants]);

  useEffect(() => {
    void reloadAll();
  }, [reloadAll]);

  async function patchUserTenant(userId: string, tenantId: number) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ tenant_id: tenantId }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(typeof data.detail === "string" ? data.detail : t("admin:tenantUpdateFailed"));
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:tenantUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }

  async function patchWorkspaceQuota(userId: string, quota: number) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ workspace_quota: quota }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(typeof data.detail === "string" ? data.detail : t("admin:workspaceQuotaUpdateFailed"));
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:workspaceQuotaUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }

  async function patchWorkspaceSelfAllowed(userId: string, allowed: boolean) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ workspace_self_allowed: allowed }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(
          typeof data.detail === "string"
            ? data.detail
            : t("admin:selfEditingPermissionUpdateFailed")
        );
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:selfEditingPermissionUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }


  async function createUser() {
    const email = newEmail.trim();
    const password = newPassword;
    const tid = parseInt(newTenantId, 10);
    if (!email || password.length < 8) {
      setCreateMsg(t("admin:usersCreateEmailPasswordRequired"));
      return;
    }
    if (!Number.isFinite(tid) || tid < 1) {
      setCreateMsg(t("admin:usersCreatePickTenant"));
      return;
    }
    setCreateMsg(null);
    setCreateBusy(true);
    try {
      const res = await apiFetch("/v1/admin/users", auth, {
        method: "POST",
        body: JSON.stringify({ email, password, role: newRole, tenant_id: tid }),
      });
      const data = (await res.json()) as {
        detail?: unknown;
        email?: string;
        role?: string;
        tenant_id?: number;
      };
      if (!res.ok) {
        setCreateMsg(typeof data.detail === "string" ? data.detail : t("admin:usersCreateFailed"));
        return;
      }
      setCreateMsg(
        t("admin:usersCreated", {
          email: data.email ?? email,
          role: data.role ?? newRole,
          tenantId: data.tenant_id ?? tid,
        })
      );
      setNewEmail("");
      setNewPassword("");
      await reloadAll();
    } catch (e) {
      setCreateMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setCreateBusy(false);
    }
  }

  async function createTenant() {
    const name = newTenantName.trim();
    if (!name) {
      setTenantCreateMsg(t("admin:usersTenantNameRequired"));
      return;
    }
    setTenantCreateMsg(null);
    setTenantCreateBusy(true);
    try {
      const res = await apiFetch("/v1/admin/tenants", auth, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      const data = (await res.json()) as { detail?: unknown; tenant?: { id: number } };
      if (!res.ok) {
        setTenantCreateMsg(typeof data.detail === "string" ? data.detail : t("admin:usersCreateFailed"));
        return;
      }
      const id = data.tenant?.id;
      setTenantCreateMsg(
        t("admin:usersTenantCreated", {
          name,
          idSuffix: id != null ? ` (id ${id})` : "",
        })
      );
      setNewTenantName("");
      await loadTenants();
      if (id != null) setNewTenantId(String(id));
    } catch (e) {
      setTenantCreateMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setTenantCreateBusy(false);
    }
  }

  const tenantOptions =
    tenants.length > 0
      ? tenants
      : [{ id: 1, name: "default" }];

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold text-white">{t("admin:usersPageTitle")}</h1>
      <p className="mt-2 text-sm text-surface-muted">
        {t("admin:usersPageIntro")}{" "}
        <Link to="/admin/tools" className="text-sky-400 hover:text-sky-300 hover:underline">
          {t("admin:adminToTools")}
        </Link>
        .
        {user?.email ? (
          <span className="ml-1 text-neutral-500">
            {t("admin:usersSignedInAs", { email: user.email })}
          </span>
        ) : null}
      </p>

      <section className="mt-8">
        <h2 className="text-sm font-medium text-white">{t("admin:usersAllAccounts")}</h2>
        <p className="mt-1 text-xs text-surface-muted">{t("admin:usersApiHint")}</p>
        <div className="mt-3 overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-surface-border bg-black/20 text-surface-muted">
              <tr>
                <th className="px-4 py-3 font-medium">{t("admin:usersColEmail")}</th>
                <th className="px-4 py-3 font-medium">{t("admin:usersColTenant")}</th>
                <th className="px-4 py-3 font-medium">{t("admin:usersColRole")}</th>
                <th className="px-4 py-3 font-medium">{t("admin:usersColQuota")}</th>
                <th className="px-4 py-3 font-medium">{t("admin:usersColSelfEdit")}</th>
                <th className="px-4 py-3 font-medium">{t("admin:usersColDiscord")}</th>
                <th className="px-4 py-3 font-medium">{t("admin:usersColTelegram")}</th>
                <th className="px-4 py-3 font-medium">{t("admin:usersColCreated")}</th>
              </tr>
            </thead>
            <tbody>
              {listLoading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-surface-muted">
                    {t("admin:loading")}
                  </td>
                </tr>
              ) : listErr ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-red-400">
                    {listErr}
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-surface-muted">
                    {t("admin:usersNoUsers")}
                  </td>
                </tr>
              ) : (
                rows.map((r) => {
                  const tid = r.tenant_id ?? 1;
                  const saving = savingUserId === r.id;
                  return (
                    <tr key={r.id} className="border-b border-surface-border/80 hover:bg-white/[0.03]">
                      <td className="px-4 py-3 text-white">
                        <span className="font-medium">{rowLabel(r)}</span>
                        {r.email?.trim() ? null : (
                          <span className="mt-0.5 block text-xs font-normal text-surface-muted">
                            {t("admin:usersNoMailbox")}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <select
                          className="max-w-[14rem] rounded-md border border-surface-border bg-black/20 px-2 py-1.5 text-xs text-white"
                          value={tid}
                          disabled={saving}
                          onChange={(e) => {
                            const next = parseInt(e.target.value, 10);
                            if (!Number.isFinite(next) || next === tid) return;
                            void patchUserTenant(r.id, next);
                          }}
                        >
                          {tenantOptions.map((row) => (
                            <option key={row.id} value={row.id}>
                              {tenantLabel(row, (key, opts) => t(key, opts))}
                            </option>
                          ))}
                        </select>
                        {saving ? (
                          <span className="ml-2 text-[10px] text-surface-muted">{t("settings:saving", { ns: "settings" })}</span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={
                            r.role?.toLowerCase() === "admin"
                              ? "rounded bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-300"
                              : "rounded bg-sky-500/20 px-2 py-0.5 text-xs text-sky-300"
                          }
                        >
                          {r.role}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="number"
                          min={1}
                          max={1000}
                          className="w-16 rounded-md border border-surface-border bg-black/20 px-2 py-1 text-xs text-white"
                          value={r.workspace_quota ?? 10}
                          disabled={saving}
                          onChange={(e) => {
                            const next = parseInt(e.target.value, 10);
                            if (!Number.isFinite(next) || next < 1 || next > 1000) return;
                            void patchWorkspaceQuota(r.id, next);
                          }}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          className="rounded border-surface-border"
                          checked={r.workspace_self_allowed ?? false}
                          disabled={saving || r.role?.toLowerCase() === "admin"}
                          onChange={(e) => void patchWorkspaceSelfAllowed(r.id, e.target.checked)}
                        />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-neutral-400">
                        {r.discord_user_id?.trim() ? r.discord_user_id.trim() : "—"}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-neutral-400">
                        {r.telegram_user_id?.trim() ? r.telegram_user_id.trim() : "—"}
                      </td>
                      <td className="px-4 py-3 text-surface-muted">
                        {r.created_at
                          ? new Date(r.created_at).toLocaleString(undefined, {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <button
          type="button"
          className="mt-2 text-xs text-sky-400 hover:text-sky-300 hover:underline"
          onClick={() => void reloadAll()}
        >
          {t("admin:usersRefreshList")}
        </button>
      </section>

      <section className="mt-10 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:usersCreateTenant")}</h2>
        <p className="mt-1 text-xs text-surface-muted">{t("admin:usersCreateTenantApi")}</p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="block text-xs text-surface-muted">
            {t("settings:displayName", { ns: "settings" })}
            <input
              type="text"
              className="mt-1 block w-full min-w-[12rem] rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={newTenantName}
              onChange={(e) => setNewTenantName(e.target.value)}
              placeholder={t("admin:tenantDisplayNamePlaceholder")}
              autoComplete="off"
            />
          </label>
          <button
            type="button"
            disabled={tenantCreateBusy}
            className="rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
            onClick={() => void createTenant()}
          >
            {tenantCreateBusy ? "…" : t("admin:usersCreateTenant")}
          </button>
        </div>
        {tenantCreateMsg ? (
          <p
            className={`mt-3 text-sm ${tenantCreateMsg.startsWith(t("admin:usersTenantCreatedPrefix")) ? "text-emerald-400" : "text-amber-400"}`}
          >
            {tenantCreateMsg}
          </p>
        ) : null}
      </section>

      <section className="mt-10 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:usersCreateUser")}</h2>
        <p className="mt-1 text-xs text-surface-muted">{t("admin:usersCreateUserApi")}</p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="block text-xs text-surface-muted">
            {t("admin:usersEmailLabel")}
            <input
              type="email"
              className="mt-1 block w-full min-w-[12rem] rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="block text-xs text-surface-muted">
            {t("admin:usersPasswordLabel")}
            <input
              type="password"
              className="mt-1 block w-full min-w-[12rem] rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          <label className="block text-xs text-surface-muted">
            {t("admin:usersTenantLabel")}
            <select
              className="mt-1 block rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={newTenantId}
              onChange={(e) => setNewTenantId(e.target.value)}
            >
              {tenantOptions.map((row) => (
                <option key={row.id} value={row.id}>
                  {tenantLabel(row, (key, opts) => t(key, opts))}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-surface-muted">
            {t("admin:usersRoleLabel")}
            <select
              className="mt-1 block rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as "user" | "admin")}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button
            type="button"
            disabled={createBusy}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            onClick={() => void createUser()}
          >
            {createBusy ? "…" : t("admin:usersCreateUser")}
          </button>
        </div>
        {createMsg ? (
          <p
            className={`mt-3 text-sm ${createMsg.startsWith(t("admin:usersCreatedPrefix")) ? "text-emerald-400" : "text-amber-400"}`}
          >
            {createMsg}
          </p>
        ) : null}
      </section>
    </div>
  );
}
