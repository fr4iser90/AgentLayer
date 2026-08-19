import { FormEvent, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { OrgKnowledgePublishSection } from "./OrgKnowledgePublishSection";

type TenantResponse = {
  tenant?: {
    id: number;
    name?: string;
    vertical_profile?: string | null;
    setup_completed_at?: string | null;
  };
  setup_required?: boolean;
};

export function OrgSetupPage() {
  const { t } = useTranslation(["org"]);
  const auth = useAuth();
  const navigate = useNavigate();
  const [wizardStep, setWizardStep] = useState(1);
  const [name, setName] = useState("");
  const [verticalProfile, setVerticalProfile] = useState("default_ops");
  const [disclaimerAccepted, setDisclaimerAccepted] = useState(false);
  const [startEmpty, setStartEmpty] = useState(false);
  const [published, setPublished] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const loadTenant = useCallback(async () => {
    try {
      const res = await apiFetch("/v1/org/tenant", auth);
      const data = (await res.json()) as TenantResponse;
      if (res.ok && data.tenant) {
        setName((data.tenant.name ?? "").trim());
        setVerticalProfile((data.tenant.vertical_profile ?? "default_ops").trim() || "default_ops");
        if (!data.setup_required) {
          navigate("/org/knowledge", { replace: true });
        }
      }
    } catch {
      /* ignore */
    }
  }, [auth, navigate]);

  useEffect(() => {
    void loadTenant();
  }, [loadTenant]);

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const res = await apiFetch("/v1/org/tenant", auth, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), vertical_profile: verticalProfile.trim() }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { detail?: string };
        setErr(typeof data.detail === "string" ? data.detail : t("org:setupFailed"));
        return;
      }
      setWizardStep(2);
    } catch {
      setErr(t("org:setupFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function finishSetup() {
    if (!disclaimerAccepted) {
      setErr(t("org:setupDisclaimerRequired"));
      return;
    }
    if (!startEmpty && !published) {
      setErr(t("org:setupContentChoiceRequired"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const res = await apiFetch("/v1/org/setup/complete", auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          disclaimer_accepted: true,
          start_empty: startEmpty,
          published_note: published,
        }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { detail?: string };
        setErr(typeof data.detail === "string" ? data.detail : t("org:setupFailed"));
        return;
      }
      await auth.refresh();
      navigate("/org/knowledge", { replace: true });
    } catch {
      setErr(t("org:setupFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-xl font-semibold text-white">{t("org:setupPageTitle")}</h1>
      <p className="mt-2 text-sm text-surface-muted">{t("org:setupPageIntro")}</p>

      {wizardStep === 1 ? (
        <form onSubmit={(e) => void saveProfile(e)} className="mt-8 space-y-4">
          <label className="block text-xs text-surface-muted" htmlFor="org-name">
            {t("org:setupOrgName")}
          </label>
          <input
            id="org-name"
            className="w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <label className="block text-xs text-surface-muted" htmlFor="org-vertical">
            {t("org:setupVerticalProfile")}
          </label>
          <input
            id="org-vertical"
            className="w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
            value={verticalProfile}
            onChange={(e) => setVerticalProfile(e.target.value)}
            required
          />
          <p className="text-[11px] text-surface-muted">{t("org:setupVerticalProfileHint")}</p>
          {err ? <p className="text-sm text-red-400">{err}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {t("org:setupContinue")}
          </button>
        </form>
      ) : null}

      {wizardStep === 2 ? (
        <div className="mt-8 space-y-6">
          <label className="flex cursor-pointer items-start gap-2 text-sm text-white">
            <input
              type="checkbox"
              className="mt-1 rounded border-surface-border"
              checked={disclaimerAccepted}
              onChange={(e) => setDisclaimerAccepted(e.target.checked)}
            />
            <span>{t("org:setupDisclaimer")}</span>
          </label>

          <div className="rounded-lg border border-surface-border p-4">
            <p className="text-sm font-medium text-white">{t("org:setupContentStep")}</p>
            <p className="mt-1 text-xs text-surface-muted">{t("org:setupContentHint")}</p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={startEmpty}
                onChange={(e) => {
                  setStartEmpty(e.target.checked);
                  if (e.target.checked) setPublished(false);
                }}
              />
              {t("org:setupStartEmpty")}
            </label>
            {!startEmpty ? (
              <div className="mt-4">
                <OrgKnowledgePublishSection onPublished={() => setPublished(true)} />
              </div>
            ) : null}
          </div>

          {err ? <p className="text-sm text-red-400">{err}</p> : null}
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            onClick={() => void finishSetup()}
          >
            {busy ? t("org:setupFinishing") : t("org:setupFinish")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
