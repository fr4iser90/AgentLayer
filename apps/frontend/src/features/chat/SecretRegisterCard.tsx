import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { buildUserSecretPostBody } from "./buildSecretPayload";
import type { SecretPromptPayload } from "./chatThreadStorage";

type Props = {
  prompt: SecretPromptPayload;
  auth: AuthContextValue;
  onSaved: (promptId: string, serviceKey: string) => void;
};

export function SecretRegisterCard({ prompt, auth, onSaved }: Props) {
  const { t } = useTranslation(["chat"]);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [rawSecret, setRawSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const disabled = prompt.status !== "pending" || saving;
  const fields = prompt.fields ?? [];
  const hasFields = fields.length > 0;

  const save = useCallback(async () => {
    setLocalError(null);
    const body = buildUserSecretPostBody(
      prompt.serviceKey,
      hasFields
        ? { title: prompt.title, help: prompt.help, fields }
        : undefined,
      fieldValues,
      rawSecret
    );
    if (!body) {
      setLocalError(t("chat:secretCardFillRequired"));
      return;
    }
    setSaving(true);
    try {
      const res = await apiFetch("/v1/user/secrets", auth, {
        method: "POST",
        body: JSON.stringify(body),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setLocalError(
          typeof data.detail === "string" ? data.detail : t("chat:secretCardSaveFailed")
        );
        return;
      }
      setFieldValues({});
      setRawSecret("");
      onSaved(prompt.promptId, prompt.serviceKey);
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [
    auth,
    fieldValues,
    hasFields,
    onSaved,
    prompt.help,
    prompt.promptId,
    prompt.serviceKey,
    prompt.title,
    rawSecret,
    t,
    fields,
  ]);

  const statusLabel =
    prompt.status === "saved"
      ? t("chat:secretCardSaved")
      : prompt.status === "error"
        ? prompt.errorMessage ?? t("chat:secretCardSaveFailed")
        : null;

  return (
    <div className="w-full max-w-[min(100%,42rem)] rounded-xl border border-amber-900/45 bg-amber-950/20 px-3 py-3 text-sm shadow-sm">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0 text-base leading-none" aria-hidden>
          🔑
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-amber-100/95">
            {prompt.title || prompt.serviceKey}
          </p>
          {prompt.reason ? (
            <p className="mt-0.5 text-[11px] text-amber-200/70">{prompt.reason}</p>
          ) : null}
          {prompt.help ? (
            <p className="mt-1 text-[11px] leading-snug text-neutral-400">{prompt.help}</p>
          ) : null}

          {prompt.status === "saved" ? (
            <p className="mt-2 text-xs text-emerald-400/90">{statusLabel}</p>
          ) : (
            <div className="mt-2 space-y-2">
              {hasFields ? (
                fields.map((f) => (
                  <label key={f.name} className="block">
                    <span className="text-[11px] text-neutral-400">
                      {f.label || f.name}
                      {f.required ? " *" : ""}
                    </span>
                    <input
                      type={f.type === "password" ? "password" : "text"}
                      autoComplete="off"
                      disabled={disabled}
                      value={fieldValues[f.name] ?? ""}
                      onChange={(e) =>
                        setFieldValues((prev) => ({ ...prev, [f.name]: e.target.value }))
                      }
                      className="mt-0.5 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-sm text-neutral-100 outline-none focus:border-amber-600/50"
                    />
                  </label>
                ))
              ) : (
                <label className="block">
                  <span className="text-[11px] text-neutral-400">{t("chat:secretCardValueLabel")}</span>
                  <input
                    type="password"
                    autoComplete="off"
                    disabled={disabled}
                    value={rawSecret}
                    onChange={(e) => setRawSecret(e.target.value)}
                    className="mt-0.5 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-1.5 text-sm text-neutral-100 outline-none focus:border-amber-600/50"
                  />
                </label>
              )}
              {localError ? (
                <p className="text-xs text-red-400/90">{localError}</p>
              ) : null}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void save()}
                  className="rounded-lg bg-amber-700/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600/90 disabled:opacity-50"
                >
                  {saving ? t("chat:secretCardSaving") : t("chat:secretCardSave")}
                </button>
                <Link
                  to="/settings/connections"
                  className="text-[11px] text-neutral-400 underline-offset-2 hover:text-neutral-300 hover:underline"
                >
                  {t("chat:secretCardOpenConnections")}
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
