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
    <div className="mx-auto max-w-page px-broad py-page">
      <h1 className="text-xl font-semibold text-ink-primary">{t("org:teamPageTitle")}</h1>
      <p className="mt-base text-sm text-ink-muted">{t("org:teamPageIntro")}</p>

      <section className="mt-deep rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("org:teamDepartments")}</h2>
        <ul className="mt-soft space-y-tight text-sm text-ink-secondary">
          {departments.map((d) => (
            <li key={d.id}>
              <span className="font-mono text-xs text-ink-muted">{d.slug}</span> — {d.name}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("org:teamProfessionRoles")}</h2>
        <ul className="mt-soft space-y-tight text-sm text-ink-secondary">
          {roles.map((r) => (
            <li key={r.id}>
              <span className="font-mono text-xs text-ink-muted">{r.slug}</span> — {r.name}{" "}
              <span className="text-ink-muted">({r.role_kind})</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("org:teamAssignments")}</h2>
        <ul className="mt-soft space-y-base text-sm text-ink-secondary">
          {assignments.map((a) => (
            <li key={a.user_id}>
              {a.user_email ?? a.user_id} → {a.profession_role_slug ?? "?"}
              {a.department_slug ? ` @ ${a.department_slug}` : ""}
            </li>
          ))}
        </ul>

        <div className="mt-wide grid gap-soft sm:grid-cols-3">
          <input
            className="rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
            placeholder={t("org:teamUserIdPlaceholder")}
            value={assignUserId}
            onChange={(e) => setAssignUserId(e.target.value)}
          />
          <select
            className="rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
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
            className="rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
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
          className="mt-soft rounded-tile bg-sky-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-sky-500"
          onClick={() => void saveAssignment()}
        >
          {t("org:teamSaveAssignment")}
        </button>
      </section>

      <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("org:teamPolicyPreview")}</h2>
        <pre className="mt-soft overflow-x-auto rounded-tile bg-black/30 p-soft text-xs text-ink-secondary">
          {policyPreview}
        </pre>
      </section>

      {msg ? <p className="mt-wide text-sm text-emerald-400">{msg}</p> : null}
      {err ? <p className="mt-wide text-sm text-red-400">{err}</p> : null}
    </div>
  );
}
