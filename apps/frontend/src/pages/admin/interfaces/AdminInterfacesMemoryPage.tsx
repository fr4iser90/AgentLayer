import { AdminInterfacesMemorySection } from "./AdminInterfacesMemorySection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

export function AdminInterfacesMemoryPage() {
  return (
    <AdminInterfacesPageShell
      title="Memory & RAG"
      description="Embedding endpoints (separate from chat), RAG tuning, memory, and memory graph."
      wide
    >
      <AdminInterfacesMemorySection />
    </AdminInterfacesPageShell>
  );
}
