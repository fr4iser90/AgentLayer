import { AdminInterfacesMemorySection } from "./AdminInterfacesMemorySection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

export function AdminInterfacesMemoryPage() {
  return (
    <AdminInterfacesPageShell
      title="Memory & RAG"
      description="Memory service, RAG ingest/search, memory graph, and docs root."
    >
      <AdminInterfacesMemorySection />
    </AdminInterfacesPageShell>
  );
}
