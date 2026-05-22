import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";

export function AdminInterfacesAutomationSection() {
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">Loading…</p>;
  }
  return (
    <>
          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Scheduler (Agent)</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Periodischer Hintergrund-Check per <span className="font-mono text-neutral-400">chat_completion</span> als
              gewählter User. Bei Bedarf Telegram an dieselbe verknüpfte User-ID — Tageslimit gegen Spam.
            </p>
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.schedulerEnabled}
                onChange={(e) => s.setSchedulerEnabled(e.target.checked)}
              />
              Scheduler aktivieren
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-interval">
              Intervall (Minuten, 5–1440)
            </label>
            <input
              id="hb-interval"
              type="number"
              min={5}
              max={1440}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerIntervalMin}
              onChange={(e) => s.setSchedulerIntervalMin(e.target.value)}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-user">
              User (Tenant/Kontext für Tools)
            </label>
            <select
              id="hb-user"
              className="mt-1 w-full max-w-xl rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerUserId}
              onChange={(e) => s.setSchedulerUserId(e.target.value)}
            >
              <option value="">— wählen —</option>
              {s.adminUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  {(u.email || u.display_name || u.id).trim() || u.id}
                </option>
              ))}
            </select>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-model">
              Modell (leer = Default)
            </label>
            <input
              id="hb-model"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerModel}
              onChange={(e) => s.setSchedulerModel(e.target.value)}
              placeholder="z. B. nemotron-3-nano:4b"
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-rounds">
              Max. Tool-Runden (leer = Server-Default)
            </label>
            <input
              id="hb-rounds"
              type="number"
              min={1}
              max={64}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerMaxRounds}
              onChange={(e) => s.setSchedulerMaxRounds(e.target.value)}
              placeholder="z. B. 4"
            />
            <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.schedulerNotifyOnlyIfNotOk}
                onChange={(e) => s.setSchedulerNotifyOnlyIfNotOk(e.target.checked)}
              />
              Nur benachrichtigen wenn nicht <span className="font-mono">SCHEDULER_OK</span> / JSON{" "}
              <span className="font-mono">notify:false</span>
            </label>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-out">
              Max. ausgehende Meldungen pro Tag (Telegram)
            </label>
            <input
              id="hb-out"
              type="number"
              min={0}
              max={100000}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerMaxOutbound}
              onChange={(e) => s.setSchedulerMaxOutbound(e.target.value)}
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-pkg">
              Tool-Packages (Allowlist, kommagetrennt) — nur bei Modus „allowlist“
            </label>
            <input
              id="hb-pkg"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerPackages}
              onChange={(e) => s.setSchedulerPackages(e.target.value)}
              placeholder="z. B. clock, openweather"
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-llm">
              LLM-Backend
            </label>
            <select
              id="hb-llm"
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerLlmBackend}
              onChange={(e) => s.setSchedulerLlmBackend(e.target.value)}
            >
              <option value="inherit">inherit (Smart-Routing wie Chat)</option>
              <option value="ollama">ollama</option>
              <option value="external">external</option>
            </select>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-tools">
              Tools-Modus
            </label>
            <select
              id="hb-tools"
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerToolsMode}
              onChange={(e) => s.setSchedulerToolsMode(e.target.value)}
            >
              <option value="none">none — nur Text, keine Tools</option>
              <option value="allowlist">allowlist — nur Packages oben</option>
              <option value="full">full — alle erlaubten Tools (Policy)</option>
            </select>
            <p className="mt-4 rounded-md border border-white/10 bg-black/20 px-3 py-2 text-xs text-surface-muted">
              Legacy IDE/PIDEA ist entfernt. Persistierte Jobs:{" "}
              <span className="font-mono text-neutral-400">general</span> (Agent{" "}
              <span className="font-mono text-neutral-400">general</span>) und{" "}
              <span className="font-mono text-neutral-400">coding</span> (Workspace-Agent{" "}
              <span className="font-mono text-neutral-400">coding</span>,{" "}
              <span className="font-mono">workspace_id</span> erforderlich). Worker-Timeout gilt für beide Ziele.
            </p>
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="hb-instr">
              Anweisungen (Prompt)
            </label>
            <textarea
              id="hb-instr"
              rows={4}
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.schedulerInstructions}
              onChange={(e) => s.setSchedulerInstructions(e.target.value)}
              placeholder="Was soll der Scheduler prüfen?"
            />
            <p className="mt-6 text-xs font-medium uppercase tracking-wide text-surface-muted">
              Persistierte Jobs (<span className="font-mono">scheduler_jobs</span>)
            </p>
            <p className="mt-1 text-xs text-surface-muted">
              Hintergrund-Thread für gespeicherte Jobs (Registry-<span className="font-mono">agent_id</span>, z. B.{" "}
              <span className="font-mono">general</span>, <span className="font-mono">coding</span>).
              Einstellungen liegen in der Datenbank (hier), nicht in Umgebungsvariablen.
            </p>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.schedulerJobsWorkerEnabled}
                onChange={(e) => s.setSchedulerJobsWorkerEnabled(e.target.checked)}
              />
              Worker aktiv (Hintergrund-Thread)
            </label>
          </section>
    </>
  );
}
