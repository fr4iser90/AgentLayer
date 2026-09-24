import {
  findCatalogRowByModelId,
  fetchModelCatalog,
  modelCatalogSelectValue,
  parseModelCatalogSelection,
  type ModelCatalogAgentlayer,
  type ModelRow,
} from "../../../lib/modelCatalog";
import { ModelCatalogSelect } from "../../../features/chat/ModelCatalogSelect";
import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

function bridgeModelSelectValue(model: string, provider: string, rows: ModelRow[]): string {
  const m = model.trim();
  if (!m) return "";
  const p = provider.trim();
  if (p) return `${p}:${m}`;
  const row = findCatalogRowByModelId(rows, m);
  return row ? modelCatalogSelectValue(row) : m;
}

export function AdminInterfacesBridgesSection() {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  const auth = useAuth();
  const [modelRows, setModelRows] = useState<ModelRow[]>([]);
  const [modelCatalogAgentlayer, setModelCatalogAgentlayer] = useState<ModelCatalogAgentlayer | null>(null);
  const [modelsLoading, setModelsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setModelsLoading(true);
    void (async () => {
      try {
        const { rows, agentlayer } = await fetchModelCatalog(auth);
        if (cancelled) return;
        setModelRows(rows);
        setModelCatalogAgentlayer(agentlayer);
      } catch {
        if (cancelled) return;
        setModelRows([]);
        setModelCatalogAgentlayer(null);
      } finally {
        if (!cancelled) setModelsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth]);

  const modelOptions = modelRows;
  if (s.loading) {
    return <p className="text-sm text-ink-muted">{t("admin:loading")}</p>;
  }
  return (
    <>
      <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:discord")}</h2>
        <p className="mt-base text-xs text-ink-muted">{t("admin:ifBridgeDiscordIntro")}</p>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="discord-id">
          {t("admin:ifBridgeDiscordAppIdLabel")}
        </label>
        <input
          id="discord-id"
          className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
          value={s.discordAppId}
          onChange={(e) => s.setDiscordAppId(e.target.value)}
          autoComplete="off"
          inputMode="numeric"
        />

        <h3 className="mt-broad text-xs font-medium uppercase tracking-wide text-ink-muted">
          {t("admin:ifBridgeInProcessBridge")}
        </h3>
        <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.bridgeEnabled}
            onChange={(e) => s.setBridgeEnabled(e.target.checked)}
          />
          {t("admin:enableDiscordBridge")}
        </label>
        <p className="mt-base text-xs text-ink-muted">
          {t("admin:tokenStoredLabel")}: {s.tokenConfigured ? t("admin:yes") : t("admin:no")}
        </p>
        <label className="mt-soft block text-xs text-ink-muted" htmlFor="d-token">
          {t("admin:discordBotTokenLabel")}
        </label>
        <input
          id="d-token"
          type="password"
          autoComplete="off"
          className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
          value={s.discordToken}
          onChange={(e) => s.setDiscordToken(e.target.value)}
          placeholder={s.tokenConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:pasteTokenPlaceholder")}
        />
        <label className="mt-soft block text-xs text-ink-muted" htmlFor="prefix">
          {t("admin:messagePrefixLabel")} <strong className="text-ink-secondary">{t("admin:empty")}</strong>{" "}
          {t("admin:messagePrefixEmptyHint")}
        </label>
        <input
          id="prefix"
          className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
          value={s.triggerPrefix}
          onChange={(e) => s.setTriggerPrefix(e.target.value)}
          placeholder={t("admin:messagePrefixPlaceholder")}
        />
        <label className="mt-soft block text-xs text-ink-muted" htmlFor="model">
          {t("admin:catalogModelIdLabel")}
        </label>
        <div id="model" className="mt-tight w-full max-w-controlWide">
          <ModelCatalogSelect
            rows={modelOptions}
            agentlayer={modelCatalogAgentlayer}
            value={bridgeModelSelectValue(s.chatModel, s.chatModelProvider, modelOptions)}
            loading={modelsLoading}
            loadingLabel={t("admin:loading")}
            emptyLabel={t("admin:ifLlmChatVisibilityEmpty")}
            ariaLabel={t("admin:catalogModelIdLabel")}
            size="md"
            onChange={(value) => {
              const parsed = parseModelCatalogSelection(value);
              s.setChatModel(parsed.modelId);
              s.setChatModelProvider(parsed.provider ?? "");
            }}
          />
        </div>
        <button
          type="button"
          className="mt-soft rounded-tile border border-line-strong bg-white/5 px-soft py-snug text-sm text-ink-primary hover:bg-white/10 disabled:opacity-40"
          disabled={!s.tokenConfigured}
          onClick={() => void s.clearDiscordToken()}
        >
          {t("admin:clearDiscordToken")}
        </button>
      </section>

      <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
        <h2 className="text-sm font-medium text-ink-primary">{t("admin:telegram")}</h2>
        <p className="mt-base text-xs text-ink-muted">{t("admin:ifBridgeTelegramIntro")}</p>
        <label className="mt-wide block text-xs text-ink-muted" htmlFor="telegram-app-hint">
          {t("admin:ifBridgeTelegramUsernameOptional")}
        </label>
        <input
          id="telegram-app-hint"
          className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
          value={s.telegramAppId}
          onChange={(e) => s.setTelegramAppId(e.target.value)}
          autoComplete="off"
          placeholder={t("admin:ifDiscordBotNamePlaceholder")}
        />

        <h3 className="mt-broad text-xs font-medium uppercase tracking-wide text-ink-muted">
          {t("admin:ifBridgeInProcessBridge")}
        </h3>
        <label className="mt-soft flex cursor-pointer items-center gap-base text-sm text-ink-primary">
          <input
            type="checkbox"
            className="rounded-tile border-line"
            checked={s.tgBridgeEnabled}
            onChange={(e) => s.setTgBridgeEnabled(e.target.checked)}
          />
          {t("admin:enableTelegramBridge")}
        </label>
        <p className="mt-base text-xs text-ink-muted">
          {t("admin:tokenStoredLabel")}: {s.tgTokenConfigured ? t("admin:yes") : t("admin:no")}
        </p>
        <label className="mt-soft block text-xs text-ink-muted" htmlFor="tg-token">
          {t("admin:telegramBotTokenLabel")}
        </label>
        <input
          id="tg-token"
          type="password"
          autoComplete="off"
          className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
          value={s.telegramToken}
          onChange={(e) => s.setTelegramToken(e.target.value)}
          placeholder={s.tgTokenConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:pasteTokenPlaceholder")}
        />
        <label className="mt-soft block text-xs text-ink-muted" htmlFor="tg-prefix">
          {t("admin:messagePrefixLabel")} <strong className="text-ink-secondary">{t("admin:empty")}</strong>{" "}
          {t("admin:messagePrefixEmptyHintTelegram")}
        </label>
        <input
          id="tg-prefix"
          className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
          value={s.tgTriggerPrefix}
          onChange={(e) => s.setTgTriggerPrefix(e.target.value)}
          placeholder={t("admin:messagePrefixPlaceholder")}
        />
        <label className="mt-soft block text-xs text-ink-muted" htmlFor="tg-model">
          {t("admin:catalogModelIdLabel")}
        </label>
        <div id="tg-model" className="mt-tight w-full max-w-controlWide">
          <ModelCatalogSelect
            rows={modelOptions}
            agentlayer={modelCatalogAgentlayer}
            value={bridgeModelSelectValue(s.tgChatModel, s.tgChatModelProvider, modelOptions)}
            loading={modelsLoading}
            loadingLabel={t("admin:loading")}
            emptyLabel={t("admin:ifLlmChatVisibilityEmpty")}
            ariaLabel={t("admin:catalogModelIdLabel")}
            size="md"
            onChange={(value) => {
              const parsed = parseModelCatalogSelection(value);
              s.setTgChatModel(parsed.modelId);
              s.setTgChatModelProvider(parsed.provider ?? "");
            }}
          />
        </div>
        <button
          type="button"
          className="mt-soft rounded-tile border border-line-strong bg-white/5 px-soft py-snug text-sm text-ink-primary hover:bg-white/10 disabled:opacity-40"
          disabled={!s.tgTokenConfigured}
          onClick={() => void s.clearTelegramToken()}
        >
          {t("admin:clearTelegramToken")}
        </button>
        <label className="mt-broad block text-xs text-ink-muted" htmlFor="http-client-log-level">
          {t("admin:ifBridgeHttpClientLogLabel")}
        </label>
        <select
          id="http-client-log-level"
          className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
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
