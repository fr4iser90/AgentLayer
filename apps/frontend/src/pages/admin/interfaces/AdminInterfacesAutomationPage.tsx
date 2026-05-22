import { Link } from "react-router-dom";
import { AdminInterfacesAutomationSection } from "./AdminInterfacesAutomationSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

export function AdminInterfacesAutomationPage() {
  return (
    <AdminInterfacesPageShell
      title="Automation"
      description={
        <>
          Operator heartbeat scheduler and{" "}
          <span className="font-mono text-neutral-300">scheduler_jobs</span> background worker. User jobs:{" "}
          <Link to="/admin/schedules" className="text-sky-400 hover:underline">
            Schedules
          </Link>
          .
        </>
      }
    >
      <AdminInterfacesAutomationSection />
    </AdminInterfacesPageShell>
  );
}
