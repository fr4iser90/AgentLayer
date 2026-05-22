import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";

export function AdminInterfacesPlatformSection() {
  const s = useOperatorSettings();
  if (s.loading) {
    return <p className="text-sm text-surface-muted">Loading…</p>;
  }
  return (
    <>
          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Agent mode</h2>
            <p className="mt-2 text-xs text-surface-muted">
              <span className="font-mono text-neutral-400">AGENT_MODE</span> in <span className="font-mono">.env</span>{" "}
              is the default (<span className="text-neutral-300">sandbox</span> = Docker-bound: tools
              always run as <span className="font-mono">container</span> for policy;
              <span className="text-neutral-300"> host</span> = allow host-class overrides per tool
              policy). Here you can override that for the running deployment (saved in the database).
              Choose &quot;Use environment&quot; to clear the override.
            </p>
            <p className="mt-2 text-xs text-surface-muted">
              Env: <span className="font-mono text-neutral-300">{s.agentModeEnv}</span>
              {" · "}
              Effective: <span className="font-mono text-neutral-300">{s.agentModeEffective}</span>
            </p>
            <label className="mt-3 block text-xs text-surface-muted" htmlFor="agent-mode">
              Operator override
            </label>
            <select
              id="agent-mode"
              className="mt-1 w-full max-w-md rounded-md border border-surface-border bg-black/20 px-3 py-2 text-sm text-white"
              value={s.agentMode}
              onChange={(e) => s.setAgentMode(e.target.value as "env" | "sandbox" | "host")}
            >
              <option value="env">Use environment (AGENT_MODE)</option>
              <option value="sandbox">sandbox (force Docker-bound tool execution)</option>
              <option value="host">host (allow host-class tool policy)</option>
            </select>
          </section>

          <section className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-medium text-white">Dashboard uploads</h2>
            <p className="mt-2 text-xs text-surface-muted">
              Globale Grenzen für Galerie-Uploads (JPEG/PNG/GIF/WebP). Leer = Umgebungsvariablen{" "}
              <span className="font-mono text-neutral-400">AGENT_DASHBOARD_UPLOAD_MAX_MB</span> /{" "}
              <span className="font-mono text-neutral-400">AGENT_DASHBOARD_UPLOAD_ALLOWED_MIME</span>
              .
            </p>
            {s.uploadEffBytes != null ? (
              <p className="mt-2 text-xs text-surface-muted">
                Aktuell wirksam: max{" "}
                <span className="font-mono text-neutral-300">{s.uploadEffBytes}</span> Bytes · MIME:{" "}
                <span className="font-mono text-neutral-300">{s.uploadEffMime.join(", ") || "—"}</span>
              </p>
            ) : null}
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="wu-mb">
              Max. Dateigröße (MB), leer = nur Env/Standard
            </label>
            <input
              id="wu-mb"
              type="number"
              min={1}
              max={512}
              className="mt-1 w-full max-w-xs rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.uploadMaxMb}
              onChange={(e) => s.setUploadMaxMb(e.target.value)}
              placeholder="z. B. 10"
            />
            <label className="mt-4 block text-xs text-surface-muted" htmlFor="wu-mime">
              Erlaubte MIME-Typen (kommagetrennt), leer = nur Env/Standard
            </label>
            <input
              id="wu-mime"
              className="mt-1 w-full rounded-md border border-surface-border bg-black/20 px-3 py-2 font-mono text-sm text-white"
              value={s.uploadMime}
              onChange={(e) => s.setUploadMime(e.target.value)}
              placeholder="image/jpeg,image/png,image/gif,image/webp"
            />
          </section>          <section className="mt-6 rounded-lg border border-surface-border p-4">
            <h3 className="text-sm font-medium text-white">Workspaces</h3>
            <p className="mt-1 text-xs text-surface-muted">
              Project workspaces for the Coding Agent.
            </p>
            <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-white">
              <input
                type="checkbox"
                className="rounded border-surface-border"
                checked={s.workspaceAllowSelfEditing}
                onChange={(e) => s.setWorkspaceAllowSelfEditing(e.target.checked)}
              />
              Erlaube Bearbeitung von AgentLayer selbst (Workspace "AgentLayer (self)")
            </label>
            <p className="mt-2 text-xs text-surface-muted">
              Wenn aktiviert, erscheint in der Coding Agent Page ein zusätzlicher Workspace der auf das
              AgentLayer-Verzeichnis (/app) zeigt. Der Agent kann dann das eigene Projekt bearbeiten.
            </p>
          </section>
    </>
  );
}
