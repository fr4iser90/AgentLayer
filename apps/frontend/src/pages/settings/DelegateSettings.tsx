import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type Level = "low" | "medium" | "high";
type PrimaryGoal = "security" | "stability" | "maintainability" | "speed";

export type DelegateConfig = {
  communication: {
    directness: Level;
    detail_level: Level;
    ask_before_major_changes: boolean;
  };
  engineering: {
    security_first: boolean;
    prefer_tests: boolean;
    prefer_refactoring: boolean;
    primary_goal: PrimaryGoal;
    priorities: PrimaryGoal[];
  };
  autonomy: {
    can_fix_minor_issues: boolean;
    can_merge_prs: boolean;
    can_force_push: boolean;
  };
  decisioning: {
    risk_tolerance: Level;
  };
  escalation: {
    ask_on_production_changes: boolean;
    ask_on_database_migrations: boolean;
    ask_on_security_findings: boolean;
  };
  goals: string[];
};

const DEFAULT_CONFIG: DelegateConfig = {
  communication: {
    directness: "medium",
    detail_level: "medium",
    ask_before_major_changes: true,
  },
  engineering: {
    security_first: true,
    prefer_tests: true,
    prefer_refactoring: false,
    primary_goal: "stability",
    priorities: ["security", "stability", "maintainability", "speed"],
  },
  autonomy: {
    can_fix_minor_issues: true,
    can_merge_prs: false,
    can_force_push: false,
  },
  decisioning: {
    risk_tolerance: "low",
  },
  escalation: {
    ask_on_production_changes: true,
    ask_on_database_migrations: true,
    ask_on_security_findings: false,
  },
  goals: [],
};

const PRIORITY_TOKENS: PrimaryGoal[] = ["security", "stability", "maintainability", "speed"];

function normPrimaryGoal(raw: unknown): PrimaryGoal {
  const s = String(raw ?? "stability").toLowerCase();
  return PRIORITY_TOKENS.includes(s as PrimaryGoal) ? (s as PrimaryGoal) : "stability";
}

function normPriorities(raw: unknown): PrimaryGoal[] {
  if (!Array.isArray(raw)) return [...DEFAULT_CONFIG.engineering.priorities];
  const out: PrimaryGoal[] = [];
  for (const item of raw) {
    const s = String(item).toLowerCase() as PrimaryGoal;
    if (PRIORITY_TOKENS.includes(s) && !out.includes(s)) out.push(s);
  }
  return out.length ? out : [...DEFAULT_CONFIG.engineering.priorities];
}

function normalizeConfig(raw: unknown): DelegateConfig {
  const r = raw as Partial<DelegateConfig> | null | undefined;
  return {
    communication: {
      directness: r?.communication?.directness ?? DEFAULT_CONFIG.communication.directness,
      detail_level: r?.communication?.detail_level ?? DEFAULT_CONFIG.communication.detail_level,
      ask_before_major_changes:
        r?.communication?.ask_before_major_changes ??
        DEFAULT_CONFIG.communication.ask_before_major_changes,
    },
    engineering: {
      security_first: r?.engineering?.security_first ?? DEFAULT_CONFIG.engineering.security_first,
      prefer_tests: r?.engineering?.prefer_tests ?? DEFAULT_CONFIG.engineering.prefer_tests,
      prefer_refactoring:
        r?.engineering?.prefer_refactoring ?? DEFAULT_CONFIG.engineering.prefer_refactoring,
      primary_goal: normPrimaryGoal(r?.engineering?.primary_goal),
      priorities: normPriorities(r?.engineering?.priorities),
    },
    autonomy: {
      can_fix_minor_issues:
        r?.autonomy?.can_fix_minor_issues ?? DEFAULT_CONFIG.autonomy.can_fix_minor_issues,
      can_merge_prs: r?.autonomy?.can_merge_prs ?? DEFAULT_CONFIG.autonomy.can_merge_prs,
      can_force_push: r?.autonomy?.can_force_push ?? DEFAULT_CONFIG.autonomy.can_force_push,
    },
    decisioning: {
      risk_tolerance: r?.decisioning?.risk_tolerance ?? DEFAULT_CONFIG.decisioning.risk_tolerance,
    },
    escalation: {
      ask_on_production_changes:
        r?.escalation?.ask_on_production_changes ??
        DEFAULT_CONFIG.escalation.ask_on_production_changes,
      ask_on_database_migrations:
        r?.escalation?.ask_on_database_migrations ??
        DEFAULT_CONFIG.escalation.ask_on_database_migrations,
      ask_on_security_findings:
        r?.escalation?.ask_on_security_findings ??
        DEFAULT_CONFIG.escalation.ask_on_security_findings,
    },
    goals: Array.isArray(r?.goals) ? r!.goals.map(String) : [],
  };
}

type WorkspaceRow = { id: string; name: string };

function LevelSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: Level;
  onChange: (v: Level) => void;
}) {
  return (
    <label className="block text-sm" htmlFor={id}>
      <span className="text-surface-muted">{label}</span>
      <select
        id={id}
        className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
        value={value}
        onChange={(e) => onChange(e.target.value as Level)}
      >
        <option value="low">low</option>
        <option value="medium">medium</option>
        <option value="high">high</option>
      </select>
    </label>
  );
}

function ConfigEditor({
  config,
  onChange,
  idPrefix,
}: {
  config: DelegateConfig;
  onChange: (c: DelegateConfig) => void;
  idPrefix: string;
}) {
  const { t } = useTranslation(["settings"]);
  const goalsText = config.goals.join("\n");
  const prioritiesText = config.engineering.priorities.join("\n");

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-sm font-medium text-white">{t("settings:delegateSectionDecisioning")}</h3>
        <p className="mt-1 text-xs text-surface-muted">{t("settings:delegateDecisioningHelp")}</p>
        <div className="mt-3">
          <LevelSelect
            id={`${idPrefix}-risk`}
            label={t("settings:delegateRiskTolerance")}
            value={config.decisioning.risk_tolerance}
            onChange={(risk_tolerance) =>
              onChange({
                ...config,
                decisioning: { risk_tolerance },
              })
            }
          />
        </div>
      </section>

      <section>
        <h3 className="text-sm font-medium text-white">{t("settings:delegateSectionEscalation")}</h3>
        <p className="mt-1 text-xs text-surface-muted">{t("settings:delegateEscalationHelp")}</p>
        <div className="mt-3 space-y-2 text-sm text-white">
          {(
            [
              ["ask_on_production_changes", t("settings:delegateEscalateProduction")],
              ["ask_on_database_migrations", t("settings:delegateEscalateDb")],
              ["ask_on_security_findings", t("settings:delegateEscalateSecurity")],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={config.escalation[key]}
                onChange={(e) =>
                  onChange({
                    ...config,
                    escalation: { ...config.escalation, [key]: e.target.checked },
                  })
                }
              />
              {label}
            </label>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-sm font-medium text-white">{t("settings:delegateSectionCommunication")}</h3>
        <div className="mt-3 flex flex-wrap gap-4">
          <LevelSelect
            id={`${idPrefix}-directness`}
            label={t("settings:delegateDirectness")}
            value={config.communication.directness}
            onChange={(directness) =>
              onChange({
                ...config,
                communication: { ...config.communication, directness },
              })
            }
          />
          <LevelSelect
            id={`${idPrefix}-detail`}
            label={t("settings:delegateDetailLevel")}
            value={config.communication.detail_level}
            onChange={(detail_level) =>
              onChange({
                ...config,
                communication: { ...config.communication, detail_level },
              })
            }
          />
        </div>
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            checked={config.communication.ask_before_major_changes}
            onChange={(e) =>
              onChange({
                ...config,
                communication: {
                  ...config.communication,
                  ask_before_major_changes: e.target.checked,
                },
              })
            }
          />
          {t("settings:delegateAskBeforeMajor")}
        </label>
      </section>

      <section>
        <h3 className="text-sm font-medium text-white">{t("settings:delegateSectionEngineering")}</h3>
        <label className="mt-3 block text-sm text-surface-muted" htmlFor={`${idPrefix}-primary-goal`}>
          {t("settings:delegatePrimaryGoal")}
        </label>
        <select
          id={`${idPrefix}-primary-goal`}
          className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
          value={config.engineering.primary_goal}
          onChange={(e) =>
            onChange({
              ...config,
              engineering: {
                ...config.engineering,
                primary_goal: e.target.value as PrimaryGoal,
              },
            })
          }
        >
          {PRIORITY_TOKENS.map((tok) => (
            <option key={tok} value={tok}>
              {tok}
            </option>
          ))}
        </select>
        <p className="mt-3 text-xs text-surface-muted">{t("settings:delegatePrioritiesHelp")}</p>
        <textarea
          className="mt-1 min-h-[72px] w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-xs text-white"
          value={prioritiesText}
          onChange={(e) => {
            const priorities = e.target.value
              .split("\n")
              .map((ln) => ln.trim().toLowerCase())
              .filter((ln): ln is PrimaryGoal =>
                PRIORITY_TOKENS.includes(ln as PrimaryGoal)
              );
            onChange({
              ...config,
              engineering: {
                ...config.engineering,
                priorities: priorities.length
                  ? priorities
                  : [...DEFAULT_CONFIG.engineering.priorities],
              },
            });
          }}
          placeholder={"security\nstability\nmaintainability\nspeed"}
        />
        <div className="mt-3 space-y-2 text-sm text-white">
          {(
            [
              ["security_first", t("settings:delegateSecurityFirst")],
              ["prefer_tests", t("settings:delegatePreferTests")],
              ["prefer_refactoring", t("settings:delegatePreferRefactoring")],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={config.engineering[key]}
                onChange={(e) =>
                  onChange({
                    ...config,
                    engineering: { ...config.engineering, [key]: e.target.checked },
                  })
                }
              />
              {label}
            </label>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-sm font-medium text-white">{t("settings:delegateSectionAutonomy")}</h3>
        <div className="mt-3 space-y-2 text-sm text-white">
          {(
            [
              ["can_fix_minor_issues", t("settings:delegateCanFixMinor")],
              ["can_merge_prs", t("settings:delegateCanMergePrs")],
              ["can_force_push", t("settings:delegateCanForcePush")],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={config.autonomy[key]}
                onChange={(e) =>
                  onChange({
                    ...config,
                    autonomy: { ...config.autonomy, [key]: e.target.checked },
                  })
                }
              />
              {label}
            </label>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-sm font-medium text-white">{t("settings:delegateSectionGoals")}</h3>
        <p className="mt-1 text-xs text-surface-muted">{t("settings:delegateGoalsHelp")}</p>
        <textarea
          className="mt-2 min-h-[100px] w-full max-w-2xl rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
          value={goalsText}
          onChange={(e) =>
            onChange({
              ...config,
              goals: e.target.value
                .split("\n")
                .map((ln) => ln.trim())
                .filter(Boolean),
            })
          }
          placeholder={t("settings:delegateGoalsPlaceholder")}
        />
      </section>
    </div>
  );
}

export function DelegateSettings() {
  const { t } = useTranslation(["settings"]);
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const [globalConfig, setGlobalConfig] = useState<DelegateConfig>(DEFAULT_CONFIG);
  const [notes, setNotes] = useState("");
  const [savingGlobal, setSavingGlobal] = useState(false);

  const [workspaces, setWorkspaces] = useState<WorkspaceRow[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceConfig, setWorkspaceConfig] = useState<DelegateConfig>(DEFAULT_CONFIG);
  const [savingWorkspace, setSavingWorkspace] = useState(false);

  const selectedWorkspace = useMemo(
    () => workspaces.find((w) => w.id === workspaceId) ?? null,
    [workspaces, workspaceId]
  );

  const loadGlobal = useCallback(async () => {
    const r = await apiFetch("/v1/user/delegate", auth);
    const data = (await r.json()) as {
      ok?: boolean;
      config?: DelegateConfig;
      notes?: string;
      delegate_storage?: string;
    };
    if (!r.ok || data.delegate_storage === "unavailable") {
      setUnavailable(true);
      return;
    }
    setUnavailable(false);
    setGlobalConfig(normalizeConfig(data.config));
    setNotes(typeof data.notes === "string" ? data.notes : "");
  }, [auth]);

  const loadWorkspace = useCallback(
    async (wid: string) => {
      if (!wid) return;
      const r = await apiFetch(`/v1/workspaces/${encodeURIComponent(wid)}/delegate`, auth);
      const data = (await r.json()) as { ok?: boolean; config?: DelegateConfig };
      if (r.ok) {
        setWorkspaceConfig(normalizeConfig(data.config));
      }
    },
    [auth]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const wsRes = await apiFetch("/v1/workspaces", auth);
      const wsData = (await wsRes.json()) as { workspaces?: { id: string; name: string }[] };
      const list = (wsData.workspaces ?? []).map((w) => ({ id: w.id, name: w.name }));
      setWorkspaces(list);
      await loadGlobal();
      if (list[0]?.id) {
        setWorkspaceId(list[0].id);
        await loadWorkspace(list[0].id);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth, loadGlobal, loadWorkspace]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (workspaceId) void loadWorkspace(workspaceId);
  }, [workspaceId, loadWorkspace]);

  const saveGlobal = async () => {
    setSavingGlobal(true);
    setMsg(null);
    try {
      const r = await apiFetch("/v1/user/delegate", auth, {
        method: "PUT",
        body: JSON.stringify({ config: globalConfig, notes }),
      });
      const data = (await r.json()) as { detail?: string };
      if (!r.ok) throw new Error(data.detail ?? t("settings:delegateSaveFailed"));
      setMsg(t("settings:delegateSaved"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingGlobal(false);
    }
  };

  const saveWorkspace = async () => {
    if (!workspaceId) return;
    setSavingWorkspace(true);
    setMsg(null);
    try {
      const r = await apiFetch(`/v1/workspaces/${encodeURIComponent(workspaceId)}/delegate`, auth, {
        method: "PUT",
        body: JSON.stringify({ config: workspaceConfig }),
      });
      const data = (await r.json()) as { detail?: string };
      if (!r.ok) throw new Error(data.detail ?? t("settings:delegateSaveFailed"));
      setMsg(t("settings:delegateWorkspaceSaved"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingWorkspace(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-surface-muted">{t("settings:agentLoading")}</p>;
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold text-white">{t("settings:delegateTitle")}</h1>
      <p className="mt-2 text-sm text-surface-muted">{t("settings:delegateSubtitle")}</p>
      <p className="mt-2 text-xs text-surface-muted">
        {t("settings:delegateVsAgent")}{" "}
        <Link to="/settings/agent" className="text-indigo-300 hover:underline">
          {t("settings:agentTitle")}
        </Link>
      </p>

      {unavailable ? (
        <p className="mt-4 text-sm text-amber-200/90">{t("settings:delegateStorageUnavailable")}</p>
      ) : null}

      {msg ? <p className="mt-4 text-sm text-neutral-300">{msg}</p> : null}

      <section className="mt-8 rounded-lg border border-surface-border bg-surface-raised/40 p-4">
        <h2 className="text-sm font-medium text-white">{t("settings:delegateGlobalTitle")}</h2>
        <ConfigEditor config={globalConfig} onChange={setGlobalConfig} idPrefix="global" />
        <label className="mt-4 block text-sm text-white" htmlFor="delegate-notes">
          {t("settings:delegateNotesLabel")}
        </label>
        <textarea
          id="delegate-notes"
          className="mt-1 min-h-[72px] w-full max-w-2xl rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={t("settings:delegateNotesPlaceholder")}
        />
        <button
          type="button"
          className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          disabled={savingGlobal || unavailable}
          onClick={() => void saveGlobal()}
        >
          {savingGlobal ? t("settings:saving") : t("settings:delegateSaveGlobal")}
        </button>
      </section>

      <section className="mt-8 rounded-lg border border-surface-border bg-surface-raised/40 p-4">
        <h2 className="text-sm font-medium text-white">{t("settings:delegateWorkspaceTitle")}</h2>
        <p className="mt-1 text-xs text-surface-muted">{t("settings:delegateWorkspaceHelp")}</p>
        {workspaces.length === 0 ? (
          <p className="mt-3 text-sm text-surface-muted">{t("settings:delegateNoWorkspaces")}</p>
        ) : (
          <>
            <label className="mt-3 block text-sm text-surface-muted" htmlFor="delegate-ws">
              {t("settings:delegateWorkspacePick")}
            </label>
            <select
              id="delegate-ws"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={workspaceId}
              onChange={(e) => setWorkspaceId(e.target.value)}
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
            {selectedWorkspace ? (
              <p className="mt-1 text-xs text-surface-muted">{selectedWorkspace.name}</p>
            ) : null}
            <div className="mt-4">
              <ConfigEditor
                config={workspaceConfig}
                onChange={setWorkspaceConfig}
                idPrefix="ws"
              />
            </div>
            <button
              type="button"
              className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
              disabled={savingWorkspace || unavailable || !workspaceId}
              onClick={() => void saveWorkspace()}
            >
              {savingWorkspace ? t("settings:saving") : t("settings:delegateSaveWorkspace")}
            </button>
          </>
        )}
      </section>
    </div>
  );
}
