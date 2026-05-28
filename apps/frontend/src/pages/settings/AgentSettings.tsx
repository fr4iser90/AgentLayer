import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type PersonaResp = {
  ok?: boolean;
  instructions?: string;
  inject_into_agent?: boolean;
  persona_storage?: string;
};

type ProfileResp = {
  ok?: boolean;
  profile_storage?: string;
  display_name?: string;
  preferred_output_language?: string;
  locale?: string;
  timezone?: string;
  tone?: string;
  verbosity?: string;
  interaction_style?: string;
  job_title?: string;
  organization?: string;
  inject_structured_profile?: boolean;
  proactive_mode?: boolean;
};

export function AgentSettings() {
  const { t } = useTranslation(["settings"]);
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [personaUnavailable, setPersonaUnavailable] = useState(false);
  const [profileUnavailable, setProfileUnavailable] = useState(false);

  const [instructions, setInstructions] = useState("");
  const [injectPersona, setInjectPersona] = useState(false);

  const [displayName, setDisplayName] = useState("");
  const [preferredOutputLanguage, setPreferredOutputLanguage] = useState("");
  const [locale, setLocale] = useState("");
  const [timezone, setTimezone] = useState("");
  const [tone, setTone] = useState("");
  const [verbosity, setVerbosity] = useState("");
  const [interactionStyle, setInteractionStyle] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [organization, setOrganization] = useState("");
  const [injectStructured, setInjectStructured] = useState(true);
  const [proactiveMode, setProactiveMode] = useState(false);

  const [savingPersona, setSavingPersona] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const [pres, prres] = await Promise.all([
        apiFetch("/v1/user/persona", auth),
        apiFetch("/v1/user/profile", auth),
      ]);
      const p = (await pres.json()) as PersonaResp;
      const r = (await prres.json()) as ProfileResp;

      if (pres.ok && p.persona_storage !== "unavailable") {
        setPersonaUnavailable(false);
        setInstructions(typeof p.instructions === "string" ? p.instructions : "");
        setInjectPersona(!!p.inject_into_agent);
      } else {
        setPersonaUnavailable(true);
        setInstructions("");
        setInjectPersona(false);
      }

      if (prres.ok && r.profile_storage !== "unavailable") {
        setProfileUnavailable(false);
        setDisplayName(String(r.display_name ?? ""));
        setPreferredOutputLanguage(String(r.preferred_output_language ?? ""));
        setLocale(String(r.locale ?? ""));
        setTimezone(String(r.timezone ?? ""));
        setTone(String(r.tone ?? ""));
        setVerbosity(String(r.verbosity ?? ""));
        setInteractionStyle(String(r.interaction_style ?? ""));
        setJobTitle(String(r.job_title ?? ""));
        setOrganization(String(r.organization ?? ""));
        setInjectStructured(r.inject_structured_profile !== false);
        setProactiveMode(!!r.proactive_mode);
      } else {
        setProfileUnavailable(true);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function savePersona() {
    setSavingPersona(true);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/user/persona", auth, {
        method: "PUT",
        body: JSON.stringify({ instructions, inject_into_agent: injectPersona }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setMsg(typeof data.detail === "string" ? data.detail : t("settings:savePersonaFailed"));
        return;
      }
      setMsg(t("settings:personaSaved"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingPersona(false);
    }
  }

  async function saveProfile() {
    setSavingProfile(true);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/user/profile", auth, {
        method: "PUT",
        body: JSON.stringify({
          display_name: displayName,
          preferred_output_language: preferredOutputLanguage,
          locale,
          timezone,
          tone,
          verbosity,
          interaction_style: interactionStyle,
          job_title: jobTitle,
          organization,
          inject_structured_profile: injectStructured,
          proactive_mode: proactiveMode,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setMsg(typeof data.detail === "string" ? data.detail : t("settings:saveProfileFailed"));
        return;
      }
      setMsg(t("settings:profileSaved"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingProfile(false);
    }
  }

  const input =
    "mt-1 block w-full rounded-md border border-surface-border bg-black/25 px-3 py-2 text-sm text-white placeholder:text-neutral-600";
  const label = "block text-xs text-surface-muted";

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-lg font-semibold text-white">{t("settings:agentTitle")}</h1>
        <p className="mt-2 text-sm text-surface-muted">
          {t("settings:agentIntro")}
        </p>
      </div>

      {loading ? <p className="text-sm text-surface-muted">{t("settings:agentLoading")}</p> : null}
      {msg ? (
        <p
          className={`text-sm ${msg.includes("saved") ? "text-emerald-400" : "text-amber-400"}`}
        >
          {msg}
        </p>
      ) : null}

      <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("settings:personaTitle")}</h2>
        <p className="mt-1 text-xs text-surface-muted">
          {t("settings:personaHelp")}
        </p>
        {personaUnavailable ? (
          <p className="mt-3 text-sm text-amber-400">
            {t("settings:personaStorageUnavailable")}
          </p>
        ) : (
          <>
            <label className={`${label} mt-4`}>
              {t("settings:personaInstructionsLabel")}
              <textarea
                className={`${input} min-h-[10rem] font-mono text-xs leading-relaxed`}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                spellCheck
              />
            </label>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-neutral-200">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-surface-border bg-black/40"
                checked={injectPersona}
                onChange={(e) => setInjectPersona(e.target.checked)}
              />
              {t("settings:personaInjectLabel")}
            </label>
            <button
              type="button"
              disabled={savingPersona}
              className="mt-4 rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
              onClick={() => void savePersona()}
            >
              {savingPersona ? t("settings:saving") : t("settings:savePersona")}
            </button>
          </>
        )}
      </section>

      <section className="rounded-xl border border-surface-border bg-black/20 p-5">
        <h2 className="text-sm font-medium text-white">{t("settings:structuredProfileTitle")}</h2>
        <p className="mt-1 text-xs text-surface-muted">
          {t("settings:structuredProfileSubtitle")}
        </p>
        {profileUnavailable ? (
          <p className="mt-3 text-sm text-amber-400">
            {t("settings:profileStorageUnavailable", { table: "user_agent_profile" })}
          </p>
        ) : (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className={label}>
              {t("settings:displayName")}
              <input className={input} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </label>
            <label className={label}>
              {t("settings:preferredOutputLanguage")}
              <input
                className={input}
                value={preferredOutputLanguage}
                onChange={(e) => setPreferredOutputLanguage(e.target.value)}
                placeholder={t("settings:preferredOutputLanguagePlaceholder")}
              />
            </label>
            <label className={label}>
              {t("settings:localeLabel")}
              <input
                className={input}
                value={locale}
                onChange={(e) => setLocale(e.target.value)}
                placeholder={t("settings:localePlaceholder")}
              />
            </label>
            <label className={label}>
              {t("settings:timezone")}
              <input
                className={input}
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                placeholder={t("settings:timezonePlaceholder")}
              />
            </label>
            <label className={label}>
              {t("settings:tone")}
              <input
                className={input}
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                placeholder={t("settings:tonePlaceholder")}
              />
            </label>
            <label className={label}>
              {t("settings:verbosity")}
              <input
                className={input}
                value={verbosity}
                onChange={(e) => setVerbosity(e.target.value)}
                placeholder={t("settings:verbosityPlaceholder")}
              />
            </label>
            <label className={`${label} sm:col-span-2`}>
              {t("settings:interactionStyle")}
              <input
                className={input}
                value={interactionStyle}
                onChange={(e) => setInteractionStyle(e.target.value)}
                placeholder={t("settings:interactionStylePlaceholder")}
              />
            </label>
            <label className={label}>
              {t("settings:jobTitle")}
              <input className={input} value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
            </label>
            <label className={label}>
              {t("settings:organization")}
              <input className={input} value={organization} onChange={(e) => setOrganization(e.target.value)} />
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-neutral-200 sm:col-span-2">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-surface-border bg-black/40"
                checked={injectStructured}
                onChange={(e) => setInjectStructured(e.target.checked)}
              />
              {t("settings:injectStructuredProfile")}
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-neutral-200 sm:col-span-2">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-surface-border bg-black/40"
                checked={proactiveMode}
                onChange={(e) => setProactiveMode(e.target.checked)}
              />
              {t("settings:proactiveMode")}
            </label>
            <div className="sm:col-span-2">
              <button
                type="button"
                disabled={savingProfile}
                className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                onClick={() => void saveProfile()}
              >
                {savingProfile ? t("settings:saving") : t("settings:saveProfile")}
              </button>
            </div>
          </div>
        )}
      </section>

      <button
        type="button"
        className="text-xs text-sky-400 hover:text-sky-300 hover:underline"
        onClick={() => void load()}
      >
        {t("settings:reloadFromServer")}
      </button>
    </div>
  );
}
