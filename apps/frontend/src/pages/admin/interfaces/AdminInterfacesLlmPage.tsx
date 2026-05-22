import { AdminInterfacesLlmSection } from "./AdminInterfacesLlmSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

export function AdminInterfacesLlmPage() {
  return (
    <AdminInterfacesPageShell
      title="LLM & routing"
      description="Chat backend, smart routing, and external OpenAI-compatible endpoints."
      wide
    >
      <AdminInterfacesLlmSection />
    </AdminInterfacesPageShell>
  );
}
