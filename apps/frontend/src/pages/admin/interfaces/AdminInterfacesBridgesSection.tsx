import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";

export function AdminInterfacesBridgesSection() {
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">Loading…</p>;
  }
  return (
    <>
          <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Discord</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Application id is a hint for integrations. The in-process bridge runs inside agent-layer; users link their
              numeric Discord user id under <strong className="text-neutral-300">Settings → Connections</strong>. With a
              trigger prefix, only messages that start with it are handled; leave the prefix field empty so the bot
              reacts to <strong className="text-neutral-300">every</strong> text message in the channel (only linked
              users; noisy in busy servers). Chat runs in-process as the linked AgentLayer user.
            </p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="discord-id">
              Discord application ID
            </label>
            <input
              id="discord-id"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.discordAppId}
              onChange={(e) => s.setDiscordAppId(e.target.value)}
              autoComplete="off"
              inputMode="numeric"
            />

            <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">In-process bridge</h3>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.bridgeEnabled}
                onChange={(e) => s.setBridgeEnabled(e.target.checked)}
              />
              Enable Discord bridge
            </label>
            <p className="mt-2 text-xs text-surface-muted">Token stored: {s.tokenConfigured ? "yes" : "no"}</p>
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="d-token">
              Discord bot token (Developer Portal)
            </label>
            <input
              id="d-token"
              type="password"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.discordToken}
              onChange={(e) => s.setDiscordToken(e.target.value)}
              placeholder={s.tokenConfigured ? "•••••• (enter new value to replace)" : "paste token"}
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="prefix">
              Message prefix (must match start of message); <strong className="text-neutral-300">empty</strong> = no
              prefix (every message is a prompt)
            </label>
            <input
              id="prefix"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.triggerPrefix}
              onChange={(e) => s.setTriggerPrefix(e.target.value)}
              placeholder="e.g. !agent  — leave empty for no prefix"
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="model">
              Ollama model id (empty = server default)
            </label>
            <input
              id="model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.chatModel}
              onChange={(e) => s.setChatModel(e.target.value)}
              placeholder="e.g. nemotron-3-nano:4b"
            />
            <button
              type="button"
              className="mt-3 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
              disabled={!s.tokenConfigured}
              onClick={() => void s.clearDiscordToken()}
            >
              Clear Discord token
            </button>
          </section>

          <section className="mt-6 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Telegram</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Bot username / hint for integrations. The in-process bridge runs inside agent-layer; users link their
              numeric Telegram user id under <strong className="text-neutral-300">Settings → Connections</strong>. With a
              trigger prefix, only messages that start with it are handled; leave the prefix field empty so the bot
              reacts to <strong className="text-neutral-300">every</strong> text message (only linked users; in groups
              set @BotFather <span className="font-mono">/setprivacy</span> to <strong className="text-neutral-300">Disable</strong>{" "}
              so the bot sees normal messages). Chat runs in-process as the linked AgentLayer user.
            </p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="telegram-app-hint">
              Telegram bot username or note (optional)
            </label>
            <input
              id="telegram-app-hint"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.telegramAppId}
              onChange={(e) => s.setTelegramAppId(e.target.value)}
              autoComplete="off"
              placeholder="@YourBotName"
            />

            <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">In-process bridge</h3>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.tgBridgeEnabled}
                onChange={(e) => s.setTgBridgeEnabled(e.target.checked)}
              />
              Enable Telegram bridge
            </label>
            <p className="mt-2 text-xs text-surface-muted">Token stored: {s.tgTokenConfigured ? "yes" : "no"}</p>
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-token">
              Telegram bot token (@BotFather)
            </label>
            <input
              id="tg-token"
              type="password"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.telegramToken}
              onChange={(e) => s.setTelegramToken(e.target.value)}
              placeholder={s.tgTokenConfigured ? "•••••• (enter new value to replace)" : "paste token"}
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-prefix">
              Message prefix (must match start of message); <strong className="text-neutral-300">empty</strong> = no
              prefix (every text message is a prompt)
            </label>
            <input
              id="tg-prefix"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.tgTriggerPrefix}
              onChange={(e) => s.setTgTriggerPrefix(e.target.value)}
              placeholder="e.g. !agent  — leave empty for no prefix"
            />
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="tg-model">
              Ollama model id (empty = server default)
            </label>
            <input
              id="tg-model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.tgChatModel}
              onChange={(e) => s.setTgChatModel(e.target.value)}
              placeholder="e.g. nemotron-3-nano:4b"
            />
            <button
              type="button"
              className="mt-3 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/10 disabled:opacity-40"
              disabled={!s.tgTokenConfigured}
              onClick={() => void s.clearTelegramToken()}
            >
              Clear Telegram token
            </button>
            <label className="mt-6 block text-xs text-surface-muted" htmlFor="http-client-log-level">
              HTTP-Client-Logging (<span className="font-mono">httpx</span> / Long-Poll) — in{" "}
              <span className="font-mono text-neutral-400">operator_settings</span>, nicht in{" "}
              <span className="font-mono text-neutral-400">.env</span>
            </label>
            <select
              id="http-client-log-level"
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.httpClientLogLevel}
              onChange={(e) => s.setHttpClientLogLevel(e.target.value)}
            >
              <option value="WARNING">WARNING — Standard (ruhig, keine Zeile pro getUpdates)</option>
              <option value="INFO">INFO — jede HTTP-Anfrage loggen (Debug)</option>
              <option value="DEBUG">DEBUG</option>
              <option value="ERROR">ERROR</option>
            </select>
          </section>
    </>
  );
}
