import type { ReactNode } from "react";
import { PageShell } from "../../../layout/PageShell";

/**
 * Interfaces pages: shared title + PageShell density.
 * `wide` → density wide (providers, routing, …); default → density default.
 */
export function AdminInterfacesPageShell({
  title,
  description,
  wide,
  children,
}: {
  title: string;
  description?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <PageShell density={wide ? "wide" : "default"}>
      <h1 className="text-2xl font-semibold text-ink-primary">{title}</h1>
      {description ? <div className="mt-base text-sm text-ink-muted">{description}</div> : null}
      <div className="mt-broad pb-24">{children}</div>
    </PageShell>
  );
}
