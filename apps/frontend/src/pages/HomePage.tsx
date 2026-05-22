import { Link } from "react-router-dom";

export function HomePage() {
  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-2xl font-semibold text-white">Agent Layer</h1>
      <p className="mt-2 text-sm text-surface-muted">
        First-party UI on the same origin as the API. Operators with the admin role can open{" "}
        <Link to="/admin" className="text-sky-400 hover:underline">
          Admin
        </Link>{" "}
        for connection keys, tools, and registry actions.
      </p>
      <ul className="mt-8 flex flex-col gap-3">
        <li>
          <Link
            to="/chat"
            className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
          >
            <span className="font-medium">Chat</span>
            <span className="mt-1 block text-sm text-surface-muted">
              Open WebUI–style shell (P2: WebSocket)
            </span>
          </Link>
        </li>
        <li>
          <Link
            to="/studio"
            className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
          >
            <span className="font-medium">Image generation</span>
            <span className="mt-1 block text-sm text-surface-muted">
              ComfyUI presets — GET /v1/studio/catalog
            </span>
          </Link>
        </li>
        <li>
          <Link
            to="/tasks"
            className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
          >
            <span className="font-medium">Tasks</span>
            <span className="mt-1 block text-sm text-surface-muted">
              Global and per-project backlog — bind a task when chatting
            </span>
          </Link>
        </li>
        <li>
          <Link
            to="/dashboard"
            className="block rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-white hover:bg-white/5"
          >
            <span className="font-medium">Dashboard</span>
            <span className="mt-1 block text-sm text-surface-muted">
              Mehrere Arten (u. a. Aufgaben, Freunde, Haustiere) — Schema einmal installieren, dann anlegen
            </span>
          </Link>
        </li>
      </ul>
      </div>
    </div>
  );
}
