import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type Department = { id: string; slug: string; name: string };
type ProfessionRole = { id: string; slug: string; name: string; role_kind: string };
type Assignment = {
  user_id: string;
  user_email?: string;
  profession_role_slug?: string;
  department_slug?: string | null;
};

export function OrgTeamPage() {
  const { t } = useTranslation(["org"]);
  const auth = useAuth();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [roles, setRoles] = useState<ProfessionRole[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [policyPreview, setPolicyPreview] = useState<string>("");
  const [assignUserId, setAssignUserId] = useState("");
  const [assignRoleId, setAssignRoleId] = useState("");
  const [assignDeptId, setAssignDeptId] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [d, r, a, p] = await Promise.all([
        apiFetch("/v1/org/departments", auth),
        apiFetch("/v1/org/profession-roles", auth),
        apiFetch("/v1/org/profession-assignments", auth),
        apiFetch("/v1/org/me/profession-policy", auth),
      ]);
      const dj = (await d.json()) as { items?: Department[] };
      const rj = (await r.json()) as { items?: ProfessionRole[] };
      const aj = (await a.json()) as { items?: Assignment[] };
      const pj = (await p.json()) as { policy?: Record<string, unknown> };
      if (d.ok) setDepartments(dj.items ?? []);
      if (r.ok) setRoles(rj.items ?? []);
      if (a.ok) setAssignments(aj.items ?? []);
      if (p.ok) setPolicyPreview(JSON.stringify(pj.policy ?? {}, null, 2));
    } catch {
      /* ignore */
    }
  }, [auth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveAssignment() {
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/org/profession-assignments", auth, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: assignUserId.trim(),
          profession_role_id: assignRoleId,
          department_id: assignDeptId || null,
        }),
      });
      const data = (await res.json()) as { detail?: string };
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : t("org:teamSaveFailed"));
        return;
      }
      setMsg(t("org:teamAssignmentSaved"));
      await load();
    } catch {
      setErr(t("org:teamSaveFailed"));
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-xl font-semibold text-white">{t("org:teamPageTitle")}</h1>
      <p className="mt-2 text-sm text-surface-muted">{t("org:teamPageIntro")}</p>

      <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("org:teamDepartments")}</h2>
        <ul className="mt-3 space-y-1 text-sm text-neutral-300">
          {departments.map((d) => (
            <li key={d.id}>
              <span className="font-mono text-xs text-surface-muted">{d.slug}</span> — {d.name}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("org:teamProfessionRoles")}</h2>
        <ul className="mt-3 space-y-1 text-sm text-neutral-300">
          {roles.map((r) => (
            <li key={r.id}>
              <span className="font-mono text-xs text-surface-muted">{r.slug}</span> — {r.name}{" "}
              <span className="text-surface-muted">({r.role_kind})</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("org:teamAssignments")}</h2>
        <ul className="mt-3 space-y-2 text-sm text-neutral-300">
          {assignments.map((a) => (
            <li key={a.user_id}>
              {a.user_email ?? a.user_id} → {a.profession_role_slug ?? "?"}
              {a.department_slug ? ` @ ${a.department_slug}` : ""}
            </li>
          ))}
        </ul>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <input
            className="rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            placeholder={t("org:teamUserIdPlaceholder")}
            value={assignUserId}
            onChange={(e) => setAssignUserId(e.target.value)}
          />
          <select
            className="rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={assignRoleId}
            onChange={(e) => setAssignRoleId(e.target.value)}
          >
            <option value="">{t("org:teamSelectRole")}</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <select
            className="rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={assignDeptId}
            onChange={(e) => setAssignDeptId(e.target.value)}
          >
            <option value="">{t("org:teamNoDepartment")}</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="mt-3 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
          onClick={() => void saveAssignment()}
        >
          {t("org:teamSaveAssignment")}
        </button>
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("org:teamPolicyPreview")}</h2>
        <pre className="mt-3 overflow-x-auto rounded bg-black/30 p-3 text-xs text-neutral-300">
          {policyPreview}
        </pre>
      </section>

      {msg ? <p className="mt-4 text-sm text-emerald-400">{msg}</p> : null}
      {err ? <p className="mt-4 text-sm text-red-400">{err}</p> : null}
    </div>
  );
}
