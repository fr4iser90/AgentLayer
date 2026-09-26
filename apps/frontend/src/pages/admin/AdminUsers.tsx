import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { hasOrgSurface } from "../../auth/deploymentMode";
import { apiFetch } from "../../lib/api";
import {
  canAssignAgents as actorCanAssignAgents,
  isTargetEditable as canEditTargetRow,
  visibleColSpan as computeVisibleColSpan,
} from "./accessGating";
import { Badge } from "../../ui/Badge";
import { Select, TextInput } from "../../ui/Field";
import { Button } from "../../ui/Button";

type TenantTemplateRow = {
  id: string;
  name: string;
  description?: string;
  vertical_profile?: string;
};

type TenantRow = { id: number; name?: string | null; vertical_profile?: string | null };

type UserRow = {
  id: string;
  email: string;
  role: string;
  site_role?: string | null;
  created_at: string;
  external_sub?: string | null;
  display_name?: string | null;
  tenant_id?: number;
  tenant_name?: string | null;
  discord_user_id?: string | null;
  telegram_user_id?: string | null;
  workspace_quota?: number;
  workspace_self_allowed?: boolean;
  schedules_allowed?: boolean;
  dashboards_allowed?: boolean;
  dashboard_quota?: number;
  media_storage_quota_mb?: number | null;
  media_enabled?: boolean | null;
  media_upload_enabled?: boolean | null;
  llm_queue_priority?: number | null;
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

// Measured on the loaded table at 1440px: every body row is 137px tall (the
// cells hold a select plus a second line of text). The loading state used to be
// one 69px row, so when the users arrived the table grew by ~1300px and shoved
// the two tenant sections out of the clipped `overflow-hidden` viewport — that
// is the 0.238 layout shift on this route. Reserving the same per-row height
// keeps those sections below the fold through the swap, and Chrome only scores
// movement that is visible, so the shift stops counting.
const SKELETON_ROW_H = 137;
const SKELETON_ROWS = 8;

function loadingRows(cols: number, loadingLabel: string) {
  return Array.from({ length: SKELETON_ROWS }, (_, i) => (
    <tr
      key={i}
      className="border-b border-line/80"
      style={{ height: `${SKELETON_ROW_H}px` }}
      aria-hidden={i === 0 ? undefined : true}
    >
      <td className="px-wide py-soft align-middle">
        {i === 0 ? <span className="sr-only">{loadingLabel}</span> : null}
        <div className="h-[14px] w-full max-w-chip animate-pulse rounded-tile bg-white/[0.07]" />
      </td>
      {Array.from({ length: Math.max(cols - 1, 0) }, (_, j) => (
        <td key={j} className="px-wide py-soft align-middle">
          <div className="h-[14px] w-full max-w-chip animate-pulse rounded-tile bg-white/[0.05]" />
        </td>
      ))}
    </tr>
  ));
}

export function AdminUsers() {
  const { t } = useTranslation(["admin", "settings"]);
  const auth = useAuth();
  const { user } = auth;
  // The tenant dimension only exists where there is an org surface. In
  // `single_user` and `agent_system` there is one tenant and nothing to pick.
  const showTenantUi = hasOrgSurface(user);
  // P6 (Weg B): platform/admin capabilities decide which rows an actor may edit and whether
  // the agent-assign column is visible. A site admin holds every capability; a delegated
  // holder only what was granted onto ``users.capabilities``.
  const actorSiteAdmin = user?.site_role === "site_admin";
  const canAssignAgents = actorCanAssignAgents(user);
  // The ``user.manage`` columns are always visible: the admin users list endpoint itself
  // already requires ``user.manage``, so every viewer is a holder. Only the agents column
  // (``agent.assign``) varies. Base column count plus Tenant in multi-tenant mode; shrink by
  // the agents column this actor may not see.
  const visibleColSpan = computeVisibleColSpan(user, !showTenantUi);
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
  const [tenantTemplates, setTenantTemplates] = useState<TenantTemplateRow[]>([]);
  const [newTenantTemplateId, setNewTenantTemplateId] = useState("");
  const [seedDemoContent, setSeedDemoContent] = useState(false);
  const [tenantCreateBusy, setTenantCreateBusy] = useState(false);
  const [tenantCreateMsg, setTenantCreateMsg] = useState<string | null>(null);

  // P3: per-user agent access. Specialist agents that can be granted beyond the
  // built-in defaults (general / knowledge_companion); admins already see all.
  const [specialistAgents, setSpecialistAgents] = useState<{ id: string; name: string }[]>([]);
  const [agentListLoaded, setAgentListLoaded] = useState(false);
  const [userAllowedAgents, setUserAllowedAgents] = useState<Record<string, Set<string>>>({});
  const [agentBusy, setAgentBusy] = useState<Record<string, boolean>>({});

  const loadTenantTemplates = useCallback(async () => {
    try {
      const res = await apiFetch("/v1/admin/tenant-templates", auth);
      const data = (await res.json()) as { items?: TenantTemplateRow[] };
      if (res.ok && Array.isArray(data.items)) {
        setTenantTemplates(data.items);
        setNewTenantTemplateId((prev) => prev || data.items?.[0]?.id || "");
      }
    } catch {
      setTenantTemplates([]);
    }
  }, [auth]);

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
    await Promise.all([loadUsers(), loadTenants(), loadTenantTemplates()]);
  }, [loadUsers, loadTenants, loadTenantTemplates]);

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

  async function patchLlmQueuePriority(userId: string, priority: number | null) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ llm_queue_priority: priority }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(typeof data.detail === "string" ? data.detail : t("admin:llmQueuePriorityUpdateFailed"));
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:llmQueuePriorityUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }

  async function patchMediaStorageQuota(userId: string, quotaMb: number) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ media_storage_quota_mb: quotaMb }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(typeof data.detail === "string" ? data.detail : t("admin:mediaQuotaUpdateFailed"));
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:mediaQuotaUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }

  async function patchMediaEnabled(userId: string, enabled: boolean) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ media_enabled: enabled }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(typeof data.detail === "string" ? data.detail : t("admin:mediaEnabledUpdateFailed"));
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:mediaEnabledUpdateFailed"));
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

  async function patchSchedulesAllowed(userId: string, allowed: boolean) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ schedules_allowed: allowed }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(
          typeof data.detail === "string" ? data.detail : t("admin:schedulesPermissionUpdateFailed")
        );
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:schedulesPermissionUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }

  async function patchDashboardsAllowed(userId: string, allowed: boolean) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ dashboards_allowed: allowed }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(
          typeof data.detail === "string" ? data.detail : t("admin:dashboardsPermissionUpdateFailed")
        );
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:dashboardsPermissionUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }

  async function patchDashboardQuota(userId: string, quota: number) {
    setSavingUserId(userId);
    setListErr(null);
    try {
      const res = await apiFetch(`/v1/admin/users/${userId}`, auth, {
        method: "PATCH",
        body: JSON.stringify({ dashboard_quota: quota }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(
          typeof data.detail === "string" ? data.detail : t("admin:dashboardsQuotaUpdateFailed")
        );
        return;
      }
      await loadUsers();
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:dashboardsQuotaUpdateFailed"));
    } finally {
      setSavingUserId(null);
    }
  }


  // Load the specialist agents once (the admin overview lists every agent).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch("/v1/admin/agents", auth);
        const data = (await res.json()) as {
          agents?: { id: string; name?: string; min_role?: string }[];
        };
        if (res.ok && Array.isArray(data.agents)) {
          const excluded = new Set(["general", "knowledge_companion", "dashboard"]);
          const specialists = data.agents
            .filter(
              (a) => !excluded.has(a.id) && (a.min_role ?? "user").toLowerCase() !== "admin"
            )
            .map((a) => ({ id: a.id, name: a.name ?? a.id }));
          if (!cancelled) setSpecialistAgents(specialists);
        }
      } catch {
        /* specialist list is best-effort */
      } finally {
        if (!cancelled) setAgentListLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth]);

  // Load each listed user's granted specialist agents so the checkboxes reflect
  // existing grants. One pass over ``rows`` (no hooks inside the loop).
  useEffect(() => {
    const pending = new Map<string, { cancelled: boolean }>();
    rows.forEach((r) => {
      const ctrl = { cancelled: false };
      pending.set(r.id, ctrl);
      void (async () => {
        try {
          const res = await apiFetch(`/v1/admin/agents/policies?user_id=${r.id}`, auth);
          const data = (await res.json()) as {
            policies?: { agent_id: string; direct_state: string; scope: string }[];
          };
          if (res.ok && Array.isArray(data.policies)) {
            const allowed = new Set(
              data.policies
                .filter((p) => p.scope === "user" && p.direct_state === "allow")
                .map((p) => p.agent_id)
            );
            if (!ctrl.cancelled) {
              setUserAllowedAgents((prev) => ({ ...prev, [r.id]: allowed }));
            }
          }
        } catch {
          /* best-effort */
        }
      })();
    });
    return () => {
      pending.forEach((c) => (c.cancelled = true));
    };
  }, [rows, auth]);

  // Grant/deny a single agent for one person (P3 batch endpoint, scope='user').
  async function toggleUserAgent(userId: string, agentId: string, allowed: boolean) {
    setAgentBusy((prev) => ({ ...prev, [userId]: true }));
    try {
      const res = await apiFetch("/v1/admin/agents/access-policy/batch", auth, {
        method: "POST",
        body: JSON.stringify({
          user_id: userId,
          agent_ids: [agentId],
          direct_state: allowed ? "allow" : "inherit",
          delegate_state: "inherit",
        }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setListErr(
          typeof data.detail === "string" ? data.detail : t("admin:agentAccessUpdateFailed")
        );
        return;
      }
      setUserAllowedAgents((prev) => {
        const next = new Set(prev[userId] ?? []);
        if (allowed) next.add(agentId);
        else next.delete(agentId);
        return { ...prev, [userId]: next };
      });
    } catch (e) {
      setListErr(e instanceof Error ? e.message : t("admin:agentAccessUpdateFailed"));
    } finally {
      setAgentBusy((prev) => ({ ...prev, [userId]: false }));
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
        !showTenantUi
          ? t("admin:usersCreatedNoTenant", {
              email: data.email ?? email,
              role: data.role ?? newRole,
            })
          : t("admin:usersCreated", {
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
        body: JSON.stringify({
          name,
          template_id: newTenantTemplateId.trim() || null,
          seed_demo_content: seedDemoContent,
        }),
      });
      const data = (await res.json()) as {
        detail?: unknown;
        tenant?: { id: number };
        template_id?: string | null;
        seeded_content?: { title?: string }[];
      };
      if (!res.ok) {
        setTenantCreateMsg(typeof data.detail === "string" ? data.detail : t("admin:usersCreateFailed"));
        return;
      }
      const id = data.tenant?.id;
      setTenantCreateMsg(
        t("admin:usersTenantCreated", {
          name,
          idSuffix: id != null ? ` (id ${id})` : "",
          templateSuffix: data.template_id ? ` · ${data.template_id}` : "",
          seedSuffix:
            data.seeded_content && data.seeded_content.length > 0
              ? ` · ${data.seeded_content.length} demo note(s)`
              : "",
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
    <div className="mx-auto max-w-page px-broad py-page">
      <h1 className="text-2xl font-semibold text-ink-primary">{t("admin:usersPageTitle")}</h1>
      <p className="mt-base text-sm text-ink-muted">
        {t("admin:usersPageIntro")}{" "}
        <Link to="/admin/tools" className="text-accent hover:text-badge-accent hover:underline">
          {t("admin:adminToTools")}
        </Link>
        .
        {user?.email ? (
          <span className="ml-tight text-ink-muted">
            {t("admin:usersSignedInAs", { email: user.email })}
          </span>
        ) : null}
      </p>

      <section className="mt-deep">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:usersAllAccounts")}</h2>
        <p className="mt-tight text-xs text-ink-muted">{t("admin:usersApiHint")}</p>
        <div className="mt-soft overflow-x-auto rounded-sheet border border-line">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-line bg-black/20 text-ink-muted">
              <tr>
                <th className="px-wide py-soft font-medium">{t("admin:usersColEmail")}</th>
                {showTenantUi && (
                  <th className="px-wide py-soft font-medium">{t("admin:usersColTenant")}</th>
                )}
                <th className="px-wide py-soft font-medium">{t("admin:usersColRole")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColQuota")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColMediaQuota")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColLlmPrio")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColMedia")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColSelfEdit")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColSchedules")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColDashboards")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColDashboardsQuota")}</th>
                {canAssignAgents && (
                  <th className="px-wide py-soft font-medium">{t("admin:usersColAgents")}</th>
                )}
                <th className="px-wide py-soft font-medium">{t("admin:usersColDiscord")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColTelegram")}</th>
                <th className="px-wide py-soft font-medium">{t("admin:usersColCreated")}</th>
              </tr>
            </thead>
            <tbody>
              {listLoading ? (
                loadingRows(visibleColSpan, t("admin:loading"))
              ) : listErr ? (
                <tr>
                  <td colSpan={visibleColSpan} className="px-wide py-broad text-center text-danger">
                    {listErr}
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={visibleColSpan} className="px-wide py-broad text-center text-ink-muted">
                    {t("admin:usersNoUsers")}
                  </td>
                </tr>
              ) : (
                rows.map((r) => {
                  const tid = r.tenant_id ?? 1;
                  const saving = savingUserId === r.id;
                  // P6: a delegated ``user.manage`` holder may edit any non-site-admin user but
                  // never a site admin (mirrors the backend PATCH boundary). Site admins may edit
                  // everyone. ``site_role`` is authoritative over the legacy ``role``.
                  const targetEditable = canEditTargetRow(user, {
                    site_role: r.site_role,
                  });
                  return (
                    <tr key={r.id} className="border-b border-line/80 hover:bg-white/[0.03]">
                      <td className="px-wide py-soft text-ink-primary">
                        <span className="font-medium">{rowLabel(r)}</span>
                        {r.email?.trim() ? null : (
                          <span className="mt-hair block text-xs font-normal text-ink-muted">
                            {t("admin:usersNoMailbox")}
                          </span>
                        )}
                      </td>
                      {showTenantUi && (
                        <td className="px-wide py-soft">
                          <Select
                            className="max-w-control text-xs"
                            value={tid}
                            disabled={saving || !targetEditable}
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
                          </Select>
                          {saving ? (
                            <span className="ml-base text-meta text-ink-muted">
                              {t("settings:saving", { ns: "settings" })}
                            </span>
                          ) : null}
                        </td>
                      )}
                      <td className="px-wide py-soft">
                        <Badge tone={r.role?.toLowerCase() === "admin" ? "success" : "accent"}>
                          {r.role}
                        </Badge>
                        {!targetEditable ? (
                          <span
                            className="mt-hair block text-xs font-normal text-warning"
                            title={t("admin:usersSiteAdminLocked")}
                          >
                            {t("admin:usersSiteAdminLocked")}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-wide py-soft">
                        <TextInput
                          type="number"
                          min={1}
                          max={1000}
                          className="w-16 text-xs"
                          value={r.workspace_quota ?? 10}
                          disabled={saving || !targetEditable}
                          onChange={(e) => {
                            const next = parseInt(e.target.value, 10);
                            if (!Number.isFinite(next) || next < 1 || next > 1000) return;
                            void patchWorkspaceQuota(r.id, next);
                          }}
                        />
                      </td>
                      <td className="px-wide py-soft">
                        <TextInput
                          type="number"
                          min={1}
                          max={50000}
                          className="w-20 text-xs"
                          value={r.media_storage_quota_mb ?? ""}
                          placeholder={t("admin:usersMediaQuotaPlaceholder")}
                          disabled={saving || !targetEditable}
                          title={t("admin:usersMediaQuotaPlaceholder")}
                          onChange={(e) => {
                            const next = parseInt(e.target.value, 10);
                            if (!Number.isFinite(next) || next < 1 || next > 50000) return;
                            void patchMediaStorageQuota(r.id, next);
                          }}
                        />
                      </td>
                      <td className="px-wide py-soft">
                        <TextInput
                          type="number"
                          min={0}
                          max={1000}
                          className="w-16 text-xs"
                          value={r.llm_queue_priority ?? ""}
                          placeholder={t("admin:usersLlmPrioDefault")}
                          disabled={saving || !targetEditable}
                          title={t("admin:usersLlmPrioHint")}
                          onChange={(e) => {
                            const raw = e.target.value.trim();
                            if (!raw) {
                              void patchLlmQueuePriority(r.id, null);
                              return;
                            }
                            const next = parseInt(raw, 10);
                            if (!Number.isFinite(next) || next < 0 || next > 1000) return;
                            void patchLlmQueuePriority(r.id, next);
                          }}
                        />
                      </td>
                      <td className="px-wide py-soft">
                        <Select
                          className="text-xs"
                          value={
                            r.media_enabled === true ? "on" : r.media_enabled === false ? "off" : "inherit"
                          }
                          disabled={saving || !targetEditable}
                          onChange={(e) => {
                            const v = e.target.value;
                            if (v === "inherit") return;
                            void patchMediaEnabled(r.id, v === "on");
                          }}
                        >
                          <option value="inherit">{t("admin:usersMediaInherit")}</option>
                          <option value="on">{t("admin:usersMediaOn")}</option>
                          <option value="off">{t("admin:usersMediaOff")}</option>
                        </Select>
                      </td>
                      <td className="px-wide py-soft">
                        <input
                          type="checkbox"
                          className="rounded-tile border-line"
                          checked={r.workspace_self_allowed ?? false}
                          disabled={saving || !targetEditable}
                          onChange={(e) => void patchWorkspaceSelfAllowed(r.id, e.target.checked)}
                        />
                      </td>
                      <td className="px-wide py-soft">
                        <input
                          type="checkbox"
                          className="rounded-tile border-line"
                          checked={r.schedules_allowed ?? false}
                          disabled={saving || !targetEditable}
                          title={t("admin:usersSchedulesHint")}
                          onChange={(e) => void patchSchedulesAllowed(r.id, e.target.checked)}
                        />
                      </td>
                      <td className="px-wide py-soft">
                        <input
                          type="checkbox"
                          className="rounded-tile border-line"
                          checked={r.dashboards_allowed ?? false}
                          disabled={saving || !targetEditable}
                          title={t("admin:usersDashboardsHint")}
                          onChange={(e) => void patchDashboardsAllowed(r.id, e.target.checked)}
                        />
                      </td>
                      <td className="px-wide py-soft">
                        <TextInput
                          type="number"
                          min={1}
                          max={1000}
                          className="w-16 text-xs"
                          value={r.dashboard_quota ?? 1}
                          placeholder={t("admin:usersDashboardsQuotaPlaceholder")}
                          title={t("admin:usersDashboardsQuotaPlaceholder")}
                          disabled={saving || !targetEditable}
                          onChange={(e) => {
                            const next = parseInt(e.target.value, 10);
                            if (!Number.isFinite(next) || next < 1 || next > 1000) return;
                            void patchDashboardQuota(r.id, next);
                          }}
                        />
                      </td>
                      {canAssignAgents && (
                      <td className="px-wide py-soft align-top">
                        {!agentListLoaded || specialistAgents.length === 0 ? (
                          <span className="text-meta text-ink-muted">
                            {t("admin:usersAgentsNone")}
                          </span>
                        ) : (
                          <div className="flex max-h-28 flex-col gap-tight overflow-y-auto pr-tight">
                            {specialistAgents.map((a) => (
                              <label
                                key={a.id}
                                className="flex items-center gap-snug text-xs text-ink-secondary"
                              >
                                <input
                                  type="checkbox"
                                  className="rounded-tile border-line"
                                  checked={userAllowedAgents[r.id]?.has(a.id) ?? false}
                                  disabled={
                                    saving ||
                                    !targetEditable ||
                                    agentBusy[r.id]
                                  }
                                  onChange={(e) =>
                                    void toggleUserAgent(r.id, a.id, e.target.checked)
                                  }
                                />
                                <span>{a.name}</span>
                              </label>
                            ))}
                          </div>
                        )}
                      </td>
                      )}
                      <td className="px-wide py-soft font-mono text-xs text-ink-muted">
                        {r.discord_user_id?.trim() ? r.discord_user_id.trim() : "—"}
                      </td>
                      <td className="px-wide py-soft font-mono text-xs text-ink-muted">
                        {r.telegram_user_id?.trim() ? r.telegram_user_id.trim() : "—"}
                      </td>
                      <td className="px-wide py-soft text-ink-muted">
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
        <Button
          variant="ghost"
          size="sm"
          type="button"
          className="mt-base text-xs text-accent hover:text-badge-accent hover:underline"
          onClick={() => void reloadAll()}
        >
          {t("admin:usersRefreshList")}
        </Button>
      </section>

      {showTenantUi && (
        <section className="mt-page rounded-sheet border border-line bg-card p-roomy">
          <h2 className="text-sm font-medium text-ink-primary">{t("admin:usersCreateTenant")}</h2>
        <p className="mt-tight text-xs text-ink-muted">{t("admin:usersCreateTenantApi")}</p>
        <div className="mt-wide flex flex-col gap-soft sm:flex-row sm:flex-wrap sm:items-end">
          <label className="block text-xs text-ink-muted">
            {t("settings:displayName", { ns: "settings" })}
            <TextInput
              type="text"
              className="mt-tight block min-w-[12rem]"
              value={newTenantName}
              onChange={(e) => setNewTenantName(e.target.value)}
              placeholder={t("admin:tenantDisplayNamePlaceholder")}
              autoComplete="off"
            />
          </label>
          <label className="block text-xs text-ink-muted">
            {t("admin:usersTenantTemplate")}
            <Select
              className="mt-tight block min-w-[14rem]"
              value={newTenantTemplateId}
              onChange={(e) => setNewTenantTemplateId(e.target.value)}
            >
              <option value="">{t("admin:usersTenantTemplateNone")}</option>
              {tenantTemplates.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.name} ({tpl.vertical_profile ?? tpl.id})
                </option>
              ))}
            </Select>
          </label>
          <label className="flex items-center gap-base text-xs text-ink-muted sm:mb-base">
            <input
              type="checkbox"
              className="rounded-tile border-line"
              checked={seedDemoContent}
              disabled={!newTenantTemplateId}
              onChange={(e) => setSeedDemoContent(e.target.checked)}
            />
            {t("admin:usersTenantSeedDemo")}
          </label>
          <Button
            variant="ghost"
            size="lg"
            type="button"
            disabled={tenantCreateBusy}
            className="bg-violet-600 px-wide py-base text-sm hover:bg-violet-500"
            onClick={() => void createTenant()}
          >
            {tenantCreateBusy ? "…" : t("admin:usersCreateTenant")}
          </Button>
        </div>
        {tenantCreateMsg ? (
          <p
            className={`mt-soft text-sm ${tenantCreateMsg.startsWith(t("admin:usersTenantCreatedPrefix")) ? "text-success" : "text-warning"}`}
          >
            {tenantCreateMsg}
          </p>
        ) : null}
      </section>
      )}

      <section className="mt-page rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:usersCreateUser")}</h2>
        <p className="mt-tight text-xs text-ink-muted">{t("admin:usersCreateUserApi")}</p>
        <div className="mt-wide flex flex-col gap-soft sm:flex-row sm:flex-wrap sm:items-end">
          <label className="block text-xs text-ink-muted">
            {t("admin:usersEmailLabel")}
            <TextInput
              type="email"
              className="mt-tight block min-w-[12rem]"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="block text-xs text-ink-muted">
            {t("admin:usersPasswordLabel")}
            <TextInput
              type="password"
              className="mt-tight block min-w-[12rem]"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          {showTenantUi && (
            <label className="block text-xs text-ink-muted">
              {t("admin:usersTenantLabel")}
              <Select
                className="mt-tight block"
                value={newTenantId}
                onChange={(e) => setNewTenantId(e.target.value)}
              >
                {tenantOptions.map((row) => (
                  <option key={row.id} value={row.id}>
                    {tenantLabel(row, (key, opts) => t(key, opts))}
                  </option>
                ))}
              </Select>
            </label>
          )}
          <label className="block text-xs text-ink-muted">
            {t("admin:usersRoleLabel")}
            <Select
              className="mt-tight block"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as "user" | "admin")}
            >
              <option value="user">user</option>
              {actorSiteAdmin && <option value="admin">admin</option>}
            </Select>
          </label>
          <Button
            variant="primary"
            size="lg"
            type="button"
            disabled={createBusy}
            className="px-wide py-base text-sm"
            onClick={() => void createUser()}
          >
            {createBusy ? "…" : t("admin:usersCreateUser")}
          </Button>
        </div>
        {createMsg ? (
          <p
            className={`mt-soft text-sm ${createMsg.startsWith(t("admin:usersCreatedPrefix")) ? "text-success" : "text-warning"}`}
          >
            {createMsg}
          </p>
        ) : null}
      </section>
    </div>
  );
}
