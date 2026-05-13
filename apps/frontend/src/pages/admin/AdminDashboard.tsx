export function AdminDashboard() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-xl font-semibold text-white">Overview</h1>
      <p className="mt-2 text-sm text-surface-muted">
        Use the sidebar for interfaces, IDE integration (placeholder), tool registry, user accounts, and scheduled jobs
        (cron). Everything here requires an admin-signed-in session.
      </p>
    </div>
  );
}
