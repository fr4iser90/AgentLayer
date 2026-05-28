import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type SecretField = {
  name: string;
  label?: string;
  type?: string;
  required?: boolean;
};

type UserSecretFormSpec = {
  title?: string;
  help?: string;
  fields?: SecretField[];
};

type ToolsMeta = {
  id?: string;
  domain?: string;
  tools?: string[];
  secrets_required?: string[];
  requires?: string[];
  TOOL_LABEL?: string;
  user_secret_forms?: Record<string, UserSecretFormSpec>;
  ui?: { display_name?: string; category?: string };
};

function secretKeysForPackage(m: ToolsMeta): string[] {
  const raw = m.secrets_required ?? [];
  if (!Array.isArray(raw)) return [];
  return [...new Set(raw.map((x) => String(x).trim().toLowerCase()).filter(Boolean))];
}

function mergeSecretForms(meta: ToolsMeta[]): Record<string, UserSecretFormSpec> {
  const out: Record<string, UserSecretFormSpec> = {};
  for (const m of meta) {
    const f = m.user_secret_forms;
    if (!f || typeof f !== "object") continue;
    for (const [k, v] of Object.entries(f)) {
      const sk = k.trim().toLowerCase();
      if (!sk || !v || typeof v !== "object") continue;
      out[sk] = v as UserSecretFormSpec;
    }
  }
  return out;
}

export function ConnectionsSettings() {
  const { t } = useTranslation(["settings", "admin"]);
  const auth = useAuth();
  const [meta, setMeta] = useState<ToolsMeta[]>([]);
  const [services, setServices] = useState<string[]>([]);
  const [secretsUnavailable, setSecretsUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  /** Which connection row is expanded (form + save for that key only). */
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [rawJson, setRawJson] = useState("");
  const [saving, setSaving] = useState(false);
  const [discordUserId, setDiscordUserId] = useState("");
  const [discordSaving, setDiscordSaving] = useState(false);
  const [telegramUserId, setTelegramUserId] = useState("");
  const [telegramSaving, setTelegramSaving] = useState(false);

  const formsByKey = useMemo(() => mergeSecretForms(meta), [meta]);

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const [tres, sres, mres] = await Promise.all([
        apiFetch("/v1/tools", auth),
        apiFetch("/v1/user/secrets", auth),
        apiFetch("/auth/me", auth),
      ]);

      const mdata = (await mres.json().catch(() => ({}))) as {
        discord_user_id?: string | null;
        telegram_user_id?: string | null;
        detail?: unknown;
      };
      if (mres.ok) {
        const d = mdata.discord_user_id;
        setDiscordUserId(d != null && String(d).trim() ? String(d).trim() : "");
        const telegramId = mdata.telegram_user_id;
        setTelegramUserId(
          telegramId != null && String(telegramId).trim() ? String(telegramId).trim() : ""
        );
      } else {
        setDiscordUserId("");
        setTelegramUserId("");
      }

      const tdata = (await tres.json()) as { tools_meta?: ToolsMeta[] };
      if (tres.ok) {
        setMeta(Array.isArray(tdata.tools_meta) ? tdata.tools_meta : []);
      } else {
        setMeta([]);
        setMsg(t("settings:toolCatalogLoadFailed"));
      }

      const sdata = (await sres.json()) as { ok?: boolean; services?: string[]; detail?: unknown };
      if (sres.status === 503) {
        setSecretsUnavailable(true);
        setServices([]);
        setMsg(
          typeof sdata.detail === "string"
            ? sdata.detail
            : t("settings:secretsOffUntilKey"),
        );
        return;
      }
      setSecretsUnavailable(false);
      if (!sres.ok) {
        setServices([]);
        if (!tres.ok) return;
        setMsg(typeof sdata.detail === "string" ? sdata.detail : t("settings:listSecretsFailed"));
        return;
      }
      setServices((sdata.services ?? []).map((k) => String(k).toLowerCase()));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  async function saveTelegramLink() {
    setMsg(null);
    setTelegramSaving(true);
    try {
      const res = await apiFetch("/v1/user/telegram", auth, {
        method: "PUT",
        body: JSON.stringify({ telegram_user_id: telegramUserId.trim() }),
      });
      const data = (await res.json()) as { ok?: boolean; telegram_user_id?: string | null; detail?: unknown };
      if (!res.ok) {
        const d = data.detail;
        setMsg(typeof d === "string" ? d : t("settings:saveTelegramFailed"));
        return;
      }
      const linkedId = data.telegram_user_id;
      setTelegramUserId(linkedId != null && String(linkedId).trim() ? String(linkedId).trim() : "");
      setMsg(t("settings:telegramSaved"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setTelegramSaving(false);
    }
  }

  async function saveDiscordLink() {
    setMsg(null);
    setDiscordSaving(true);
    try {
      const res = await apiFetch("/v1/user/discord", auth, {
        method: "PUT",
        body: JSON.stringify({ discord_user_id: discordUserId.trim() }),
      });
      const data = (await res.json()) as { ok?: boolean; discord_user_id?: string | null; detail?: unknown };
      if (!res.ok) {
        const d = data.detail;
        setMsg(typeof d === "string" ? d : t("settings:saveDiscordFailed"));
        return;
      }
      const d = data.discord_user_id;
      setDiscordUserId(d != null && String(d).trim() ? String(d).trim() : "");
      setMsg(t("settings:discordSaved"));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setDiscordSaving(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  const keyUsage = useMemo(() => {
    const map = new Map<string, { ids: string[]; labels: string[] }>();
    for (const m of meta) {
      const pid = (m.id || "").trim() || "—";
      const label = (m.ui?.display_name || m.TOOL_LABEL || m.id || "").trim() || pid;
      for (const k of secretKeysForPackage(m)) {
        if (!map.has(k)) map.set(k, { ids: [], labels: [] });
        const e = map.get(k)!;
        if (!e.ids.includes(pid)) e.ids.push(pid);
        if (!e.labels.includes(label)) e.labels.push(label);
      }
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [meta]);

  const catalogKeys = useMemo(() => keyUsage.map(([k]) => k), [keyUsage]);

  const activeForm = activeKey ? formsByKey[activeKey] : undefined;

  useEffect(() => {
    setFieldValues({});
    setRawJson("");
  }, [activeKey]);

  async function saveSecret() {
    const sk = (activeKey ?? "").trim().toLowerCase();
    if (!sk) {
      setMsg(t("settings:connectionsPickConnectionFirst"));
      return;
    }

    let payload: { service_key: string; secret: string | Record<string, string> };

    if (activeForm?.fields?.length) {
      const obj: Record<string, string> = {};
      for (const f of activeForm.fields) {
        const n = f.name;
        let v = (fieldValues[n] ?? "").trim();
        if (n === "app_password") v = v.replace(/\s+/g, "");
        obj[n] = v;
      }
      const missing = activeForm.fields.filter((f) => f.required && !obj[f.name]?.trim());
      if (missing.length) {
        setMsg(
          t("settings:connectionsPleaseFill", {
            fields: missing.map((f) => f.label || f.name).join(", "),
          })
        );
        return;
      }
      payload = { service_key: sk, secret: obj };
    } else {
      const raw = rawJson.trim();
      if (!raw) {
        setMsg(t("settings:connectionsSecretRequired"));
        return;
      }
      try {
        const parsed = JSON.parse(raw) as unknown;
        payload =
          typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
            ? { service_key: sk, secret: parsed as Record<string, string> }
            : { service_key: sk, secret: raw };
      } catch {
        payload = { service_key: sk, secret: raw };
      }
    }

    setSaving(true);
    setMsg(null);
    try {
      const res = await apiFetch("/v1/user/secrets", auth, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setMsg(typeof data.detail === "string" ? data.detail : t("settings:connectionsSaveFailed"));
        return;
      }
      setMsg(t("settings:connectionsSaved"));
      setFieldValues({});
      setRawJson("");
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function deleteSecret(key: string) {
    if (!confirm(t("settings:connectionsRemoveSecretConfirm", { key }))) return;
    setMsg(null);
    try {
      const res = await apiFetch(`/v1/user/secrets/${encodeURIComponent(key)}`, auth, {
        method: "DELETE",
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      if (!res.ok) {
        setMsg(typeof data.detail === "string" ? data.detail : t("settings:connectionsDeleteFailed"));
        return;
      }
      setMsg(t("settings:connectionsRemoved"));
      if (activeKey === key) {
        setActiveKey(null);
      }
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  const orphanServices = services.filter((s) => !catalogKeys.includes(s));

  function toggleKey(key: string) {
    setMsg(null);
    setActiveKey((prev) => (prev === key ? null : key));
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-lg font-semibold text-white">{t("settings:connectionsTitle")}</h1>
        <p className="mt-2 text-sm text-surface-muted">{t("settings:connectionsIntro")}</p>
      </div>

      {loading ? <p className="text-sm text-surface-muted">{t("settings:agentLoading")}</p> : null}

      <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:discord")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("settings:connectionsDiscordIntro")}</p>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="discord-user-id">
          {t("settings:connectionsDiscordIdLabel")}
        </label>
        <input
          id="discord-user-id"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={discordUserId}
          onChange={(e) => setDiscordUserId(e.target.value.replace(/\D/g, ""))}
          autoComplete="off"
          inputMode="numeric"
          placeholder={t("settings:discordUserIdPlaceholder")}
          spellCheck={false}
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={discordSaving}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            onClick={() => void saveDiscordLink()}
          >
            {discordSaving ? t("settings:saving") : t("settings:connectionsSaveDiscord")}
          </button>
          <button
            type="button"
            disabled={discordSaving || !discordUserId}
            className="rounded-md border border-white/15 bg-white/5 px-4 py-2 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
            onClick={() => {
              setDiscordUserId("");
              void (async () => {
                setDiscordSaving(true);
                setMsg(null);
                try {
                  const res = await apiFetch("/v1/user/discord", auth, {
                    method: "PUT",
                    body: JSON.stringify({ discord_user_id: "" }),
                  });
                  const data = (await res.json()) as { detail?: unknown };
                  if (!res.ok) {
                    setMsg(typeof data.detail === "string" ? data.detail : t("settings:connectionsClearLinkFailed"));
                    await load();
                    return;
                  }
                  setMsg(t("settings:connectionsDiscordRemoved"));
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : String(e));
                } finally {
                  setDiscordSaving(false);
                }
              })();
            }}
          >
            {t("settings:connectionsClearDiscord")}
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:telegram")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("settings:connectionsTelegramIntro")}</p>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="telegram-user-id">
          {t("settings:connectionsTelegramIdLabel")}
        </label>
        <input
          id="telegram-user-id"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={telegramUserId}
          onChange={(e) => setTelegramUserId(e.target.value.replace(/\D/g, ""))}
          autoComplete="off"
          inputMode="numeric"
          placeholder={t("settings:telegramUserIdPlaceholder")}
          spellCheck={false}
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={telegramSaving}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            onClick={() => void saveTelegramLink()}
          >
            {telegramSaving ? t("settings:saving") : t("settings:connectionsSaveTelegram")}
          </button>
          <button
            type="button"
            disabled={telegramSaving || !telegramUserId}
            className="rounded-md border border-white/15 bg-white/5 px-4 py-2 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
            onClick={() => {
              setTelegramUserId("");
              void (async () => {
                setTelegramSaving(true);
                setMsg(null);
                try {
                  const res = await apiFetch("/v1/user/telegram", auth, {
                    method: "PUT",
                    body: JSON.stringify({ telegram_user_id: "" }),
                  });
                  const data = (await res.json()) as { detail?: unknown };
                  if (!res.ok) {
                    setMsg(typeof data.detail === "string" ? data.detail : t("settings:connectionsClearLinkFailed"));
                    await load();
                    return;
                  }
                  setMsg(t("settings:connectionsTelegramRemoved"));
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : String(e));
                } finally {
                  setTelegramSaving(false);
                }
              })();
            }}
          >
            {t("settings:connectionsClear")}
          </button>
        </div>
      </section>

      {msg ? (
        <p
          className={`text-sm ${
            msg === t("settings:connectionsSaved") ||
            msg === t("settings:connectionsRemoved") ||
            msg === t("settings:discordSaved") ||
            msg === t("settings:telegramSaved") ||
            msg === t("settings:connectionsDiscordRemoved") ||
            msg === t("settings:connectionsTelegramRemoved")
              ? "text-emerald-400"
              : "text-amber-400"
          }`}
        >
          {msg}
        </p>
      ) : null}

      <section className="rounded-xl border border-surface-border bg-surface-raised">
        <div className="border-b border-surface-border px-4 py-3">
          <h2 className="text-sm font-medium text-white">{t("settings:connectionsCatalogTitle")}</h2>
          <p className="mt-0.5 text-xs text-surface-muted">{t("settings:connectionsCatalogHint")}</p>
        </div>
        <ul className="divide-y divide-white/5">
          {keyUsage.length === 0 && !loading ? (
            <li className="px-4 py-6 text-sm text-surface-muted">{t("settings:connectionsCatalogEmpty")}</li>
          ) : (
            keyUsage.map(([key, info]) => {
              const saved = services.includes(key);
              const hasForm = !!formsByKey[key];
              const open = activeKey === key;
              return (
                <li key={key} className="overflow-hidden">
                  <button
                    type="button"
                    onClick={() => toggleKey(key)}
                    className="flex w-full flex-col gap-2 px-4 py-4 text-left transition hover:bg-white/[0.03] sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm text-white">{key}</span>
                        {hasForm ? (
                          <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] text-sky-200">
                            {t("settings:connectionsFormInUiBadge")}
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-1 text-xs text-surface-muted">
                        {t("settings:connectionsPackages", {
                          labels:
                            info.labels.slice(0, 4).join(", ") +
                            (info.labels.length > 4 ? ` +${info.labels.length - 4}` : ""),
                        })}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span
                        className={
                          saved
                            ? "rounded bg-emerald-500/15 px-2 py-1 text-xs text-emerald-300"
                            : "rounded bg-neutral-500/20 px-2 py-1 text-xs text-neutral-300"
                        }
                      >
                        {saved ? t("settings:connectionsSecretSaved") : t("settings:connectionsSecretNotSaved")}
                      </span>
                      <span className="text-xs text-surface-muted">{open ? "▲" : "▼"}</span>
                    </div>
                  </button>

                  {open ? (
                    <div className="space-y-4 border-t border-white/5 bg-black/20 px-4 py-4">
                      {saved && !secretsUnavailable ? (
                        <div className="flex justify-end">
                          <button
                            type="button"
                            className="text-xs text-red-400/90 hover:text-red-300 hover:underline"
                            onClick={(e) => {
                              e.stopPropagation();
                              void deleteSecret(key);
                            }}
                          >
                            {t("settings:connectionsRemoveStoredSecret")}
                          </button>
                        </div>
                      ) : null}

                        {activeForm?.help || activeForm?.title ? (
                        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs leading-relaxed text-neutral-300">
                          {activeForm.title ? (
                            <p className="mb-1 font-medium text-neutral-200">{activeForm.title}</p>
                          ) : null}
                          <p className="text-surface-muted">{activeForm.help}</p>
                        </div>
                      ) : null}

                      {activeForm?.fields?.length ? (
                        <div className="space-y-3">
                          {activeForm.fields.map((f) => {
                            const id = `sec-${key}-${f.name}`;
                            const fieldType = (f.type || "text").toLowerCase();
                            const inputType =
                              fieldType === "password" ? "password" : fieldType === "email" ? "email" : "text";
                            return (
                              <label key={f.name} className="block text-xs text-surface-muted" htmlFor={id}>
                                {f.label || f.name}
                                {f.required ? <span className="text-amber-400/80"> *</span> : null}
                                <input
                                  id={id}
                                  type={inputType}
                                  autoComplete="off"
                                  className="mt-1 block w-full rounded-md border border-surface-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-neutral-600"
                                  value={fieldValues[f.name] ?? ""}
                                  onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
                                  disabled={secretsUnavailable}
                                />
                              </label>
                            );
                          })}
                        </div>
                      ) : (
                        <label className="block text-xs text-surface-muted">
                          {t("settings:connectionsSecretLabel")}
                          <textarea
                            className="mt-1 min-h-[7rem] w-full rounded-md border border-surface-border bg-black/30 px-3 py-2 font-mono text-xs text-white placeholder:text-neutral-600"
                            placeholder={t("settings:connectionsSecretJsonPlaceholder")}
                            value={rawJson}
                            onChange={(e) => setRawJson(e.target.value)}
                            disabled={secretsUnavailable}
                            spellCheck={false}
                          />
                        </label>
                      )}

                      <button
                        type="button"
                        disabled={saving || secretsUnavailable}
                        className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-40"
                        onClick={() => void saveSecret()}
                      >
                        {saving ? t("settings:saving") : t("admin:save")}
                      </button>
                    </div>
                  ) : null}
                </li>
              );
            })
          )}
        </ul>
      </section>

      {orphanServices.length > 0 ? (
        <section className="rounded-xl border border-surface-border bg-black/20 p-5">
          <h2 className="text-sm font-medium text-white">{t("settings:connectionsOrphanTitle")}</h2>
          <p className="mt-1 text-xs text-surface-muted">{t("settings:connectionsOrphanIntro")}</p>
          <ul className="mt-3 divide-y divide-white/5 rounded-lg border border-white/10">
            {orphanServices.map((k) => {
              const open = activeKey === k;
              return (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => toggleKey(k)}
                    className="flex w-full items-center justify-between px-3 py-3 text-left text-sm hover:bg-white/[0.03]"
                  >
                    <span className="font-mono text-white">{k}</span>
                    <span className="text-xs text-surface-muted">{open ? "▲" : "▼"}</span>
                  </button>
                  {open ? (
                    <div className="space-y-3 border-t border-white/5 px-3 py-3">
                      <label className="block text-xs text-surface-muted">
                        {t("settings:connectionsSecretLabel")}
                        <textarea
                          className="mt-1 min-h-[6rem] w-full rounded-md border border-surface-border bg-black/30 px-3 py-2 font-mono text-xs text-white"
                          value={rawJson}
                          onChange={(e) => setRawJson(e.target.value)}
                          disabled={secretsUnavailable}
                          spellCheck={false}
                        />
                      </label>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={saving || secretsUnavailable}
                          className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-40"
                          onClick={() => void saveSecret()}
                        >
                          {saving ? t("settings:saving") : t("admin:save")}
                        </button>
                        <button
                          type="button"
                          className="text-xs text-red-400/90 hover:text-red-300 hover:underline"
                          onClick={() => void deleteSecret(k)}
                        >
                          {t("settings:connectionsRemove")}
                        </button>
                      </div>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <p className="text-xs text-surface-muted">{t("settings:connectionsToolAuthorsHint")}</p>

      <p className="text-xs text-surface-muted">
        {t("settings:connectionsEndUserTools")}{" "}
        <Link to="/settings/tools" className="text-sky-400 hover:text-sky-300 hover:underline">
          {t("settings:toolsTitle")}
        </Link>
        .
      </p>

      <button
        type="button"
        className="text-xs text-sky-400 hover:text-sky-300 hover:underline"
        onClick={() => void load()}
      >
        {t("settings:profileRefresh")}
      </button>
    </div>
  );
}
