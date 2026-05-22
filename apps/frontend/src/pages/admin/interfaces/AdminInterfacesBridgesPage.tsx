import { AdminInterfacesBridgesSection } from "./AdminInterfacesBridgesSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

export function AdminInterfacesBridgesPage() {
  return (
    <AdminInterfacesPageShell
      title="Bridges"
      description="Discord and Telegram in-process gateways. Users link accounts under Settings → Connections."
    >
      <AdminInterfacesBridgesSection />
    </AdminInterfacesPageShell>
  );
}
