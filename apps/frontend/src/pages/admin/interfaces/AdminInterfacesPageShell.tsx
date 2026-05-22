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
    <div className={`mx-auto px-6 py-8 ${wide ? "max-w-4xl" : "max-w-2xl"}`}>
      <h1 className="text-2xl font-semibold text-white">{title}</h1>
      {description ? <div className="mt-2 text-sm text-surface-muted">{description}</div> : null}
      <div className="mt-6 pb-24">{children}</div>
    </div>
  );
}
