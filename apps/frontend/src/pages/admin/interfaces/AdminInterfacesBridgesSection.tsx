import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { useTranslation } from "react-i18next";

export function AdminInterfacesBridgesSection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">{t("admin:loading")}</p>;
  }
  return (
    <>
      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:discord")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifBridgeDiscordIntro")}</p>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="discord-id">
          {t("admin:ifBridgeDiscordAppIdLabel")}
        </label>
        <input
          id="discord-id"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.discordAppId}
          onChange={(e) => s.setDiscordAppId(e.target.value)}
          autoComplete="off"
          inputMode="numeric"
        />

        <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">
          {t("admin:ifBridgeInProcessBridge")}
        </h3>
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.bridgeEnabled}
            onChange={(e) => s.setBridgeEnabled(e.target.checked)}
          />
          {t("admin:enableDiscordBridge")}
        </label>
        <p className="mt-2 text-xs text-surface-muted">
          {t("admin:tokenStoredLabel")}: {s.tokenConfigured ? t("admin:yes") : t("admin:no")}
        </p>
        <label className="mt-3 block text-xs text-surface-muted" htmlFor="d-token">
          {t("admin:discordBotTokenLabel")}
        </label>
        <input
          id="d-token"
          type="password"
          autoComplete="off"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.discordToken}
          onChange={(e) => s.setDiscordToken(e.target.value)}
          placeholder={s.tokenConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:pasteTokenPlaceholder")}
        />
        <label className="mt-3 block text-xs text-surface-muted" htmlFor="prefix">
          {t("admin:messagePrefixLabel")} <strong className="text-neutral-300">{t("admin:empty")}</strong>{" "}
          {t("admin:messagePrefixEmptyHint")}
        </label>
        <input
          id="prefix"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.triggerPrefix}
          onChange={(e) => s.setTriggerPrefix(e.target.value)}
          placeholder={t("admin:messagePrefixPlaceholder")}
        />
        <label className="mt-3 block text-xs text-surface-muted" htmlFor="model">
          {t("admin:catalogModelIdLabel")}
        </label>
        <input
          id="model"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.chatModel}
          onChange={(e) => s.setChatModel(e.target.value)}
          placeholder={t("admin:catalogModelIdPlaceholder")}
        />
        <button
          type="button"
          className="mt-3 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
          disabled={!s.tokenConfigured}
          onClick={() => void s.clearDiscordToken()}
        >
          {t("admin:clearDiscordToken")}
        </button>
      </section>

      <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-medium text-white">{t("admin:telegram")}</h2>
        <p className="mt-2 text-xs text-surface-muted">{t("admin:ifBridgeTelegramIntro")}</p>
        <label className="mt-4 block text-xs text-surface-muted" htmlFor="telegram-app-hint">
          {t("admin:ifBridgeTelegramUsernameOptional")}
        </label>
        <input
          id="telegram-app-hint"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.telegramAppId}
          onChange={(e) => s.setTelegramAppId(e.target.value)}
          autoComplete="off"
          placeholder={t("admin:ifDiscordBotNamePlaceholder")}
        />

        <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">
          {t("admin:ifBridgeInProcessBridge")}
        </h3>
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
          <input
            type="checkbox"
            className="rounded border-surface-border"
            checked={s.tgBridgeEnabled}
            onChange={(e) => s.setTgBridgeEnabled(e.target.checked)}
          />
          {t("admin:enableTelegramBridge")}
        </label>
        <p className="mt-2 text-xs text-surface-muted">
          {t("admin:tokenStoredLabel")}: {s.tgTokenConfigured ? t("admin:yes") : t("admin:no")}
        </p>
        <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-token">
          {t("admin:telegramBotTokenLabel")}
        </label>
        <input
          id="tg-token"
          type="password"
          autoComplete="off"
          className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.telegramToken}
          onChange={(e) => s.setTelegramToken(e.target.value)}
          placeholder={s.tgTokenConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:pasteTokenPlaceholder")}
        />
        <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-prefix">
          {t("admin:messagePrefixLabel")} <strong className="text-neutral-300">{t("admin:empty")}</strong>{" "}
          {t("admin:messagePrefixEmptyHintTelegram")}
        </label>
        <input
          id="tg-prefix"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.tgTriggerPrefix}
          onChange={(e) => s.setTgTriggerPrefix(e.target.value)}
          placeholder={t("admin:messagePrefixPlaceholder")}
        />
        <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-model">
          {t("admin:catalogModelIdLabel")}
        </label>
        <input
          id="tg-model"
          className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.tgChatModel}
          onChange={(e) => s.setTgChatModel(e.target.value)}
          placeholder={t("admin:catalogModelIdPlaceholder")}
        />
        <button
          type="button"
          className="mt-3 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
          disabled={!s.tgTokenConfigured}
          onClick={() => void s.clearTelegramToken()}
        >
          {t("admin:clearTelegramToken")}
        </button>
        <label className="mt-6 block text-xs text-surface-muted" htmlFor="http-client-log-level">
          {t("admin:ifBridgeHttpClientLogLabel")}
        </label>
        <select
          id="http-client-log-level"
          className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
          value={s.httpClientLogLevel}
          onChange={(e) => s.setHttpClientLogLevel(e.target.value)}
        >
          <option value="WARNING">{t("admin:httpClientLogWarning")}</option>
          <option value="INFO">{t("admin:httpClientLogInfo")}</option>
          <option value="DEBUG">{t("admin:ifBridgeHttpLogDebug")}</option>
          <option value="ERROR">{t("admin:ifBridgeHttpLogError")}</option>
        </select>
      </section>
    </>
  );
}
