import type { ReactNode } from "react";

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
    <div className={`mx-auto px-broad py-deep ${wide ? "max-w-page" : "max-w-pageNarrow"}`}>
      <h1 className="text-2xl font-semibold text-ink-primary">{title}</h1>
      {description ? <div className="mt-base text-sm text-ink-muted">{description}</div> : null}
      <div className="mt-broad pb-24">{children}</div>
    </div>
  );
}
