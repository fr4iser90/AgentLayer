import { AdminInterfacesLlmSection } from "./AdminInterfacesLlmSection";
import { AdminInterfacesPageShell } from "./AdminInterfacesPageShell";

export function AdminInterfacesLlmPage() {
  return (
    <AdminInterfacesPageShell
      title="LLM & routing"
      description="Chat providers (OpenAI-compatible endpoints), optional smart routing."
      wide
    >
      <AdminInterfacesLlmSection />
    </AdminInterfacesPageShell>
  );
}
