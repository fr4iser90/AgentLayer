import { AdminInterfacesPlatformSection } from "./AdminInterfacesPlatformSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

export function AdminInterfacesPlatformPage() {
  return (
    <AdminInterfacesPageShell
      title="Platform"
      description="Agent execution mode, dashboard upload limits, and workspace self-edit."
    >
      <AdminInterfacesPlatformSection />
    </AdminInterfacesPageShell>
  );
}
