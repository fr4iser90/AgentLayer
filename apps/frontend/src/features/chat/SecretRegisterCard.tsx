import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";
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
      rawSecret,
      {
        scope: prompt.scope === "workspace" ? "workspace" : "global",
        workspaceId: prompt.workspaceId,
      }
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
    prompt.scope,
    prompt.workspaceId,
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
    <div className="w-full max-w-measure rounded-sheet border border-warning/45 bg-warning-subtle px-soft py-soft text-sm shadow-sm">
      <div className="flex items-start gap-base">
        <KeyRound aria-hidden className="mt-hair h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-badge-warning">
            {prompt.title || prompt.serviceKey}
          </p>
          {prompt.reason ? (
            <p className="mt-hair text-meta text-badge-warning">{prompt.reason}</p>
          ) : null}
          {prompt.help ? (
            <p className="mt-tight text-meta leading-snug text-ink-muted">{prompt.help}</p>
          ) : null}

          {prompt.status === "saved" ? (
            <p className="mt-base text-xs text-success">{statusLabel}</p>
          ) : (
            <div className="mt-base space-y-base">
              {hasFields ? (
                fields.map((f) => (
                  <label key={f.name} className="block">
                    <span className="text-meta text-ink-muted">
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
                      className="mt-hair w-full rounded-card border border-line bg-field px-firm py-snug text-sm text-ink-primary outline-none focus:border-warning/50"
                    />
                  </label>
                ))
              ) : (
                <label className="block">
                  <span className="text-meta text-ink-muted">{t("chat:secretCardValueLabel")}</span>
                  <input
                    type="password"
                    autoComplete="off"
                    disabled={disabled}
                    value={rawSecret}
                    onChange={(e) => setRawSecret(e.target.value)}
                    className="mt-hair w-full rounded-card border border-line bg-field px-firm py-snug text-sm text-ink-primary outline-none focus:border-warning/50"
                  />
                </label>
              )}
              {localError ? (
                <p className="text-xs text-danger">{localError}</p>
              ) : null}
              <div className="flex flex-wrap items-center gap-base pt-tight">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void save()}
                  className="rounded-card bg-warning px-soft py-snug text-xs font-medium text-ink-primary hover:bg-warning-hover disabled:opacity-50"
                >
                  {saving ? t("chat:secretCardSaving") : t("chat:secretCardSave")}
                </button>
                <Link
                  to="/settings/connections"
                  className="text-meta text-ink-muted underline-offset-2 hover:text-neutral-300 hover:underline"
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
