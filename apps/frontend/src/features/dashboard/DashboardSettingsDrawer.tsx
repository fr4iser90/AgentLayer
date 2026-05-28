import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export function DashboardSettingsDrawer(props: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { open, title, onClose, children } = props;
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label={t("dashboard:closeSettings")}
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />
      <aside className="relative flex h-full max-h-[100dvh] w-full max-w-xl flex-col overflow-hidden border-l border-surface-border bg-surface-raised shadow-xl">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-surface-border px-4 py-3">
          <p className="min-w-0 truncate text-sm font-medium text-white">{title}</p>
          <button
            type="button"
            className="rounded-md px-2 py-1 text-xs text-surface-muted hover:bg-white/5 hover:text-neutral-200"
            onClick={onClose}
          >
            {t("dashboard:close")}
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain p-4">{children}</div>
      </aside>
    </div>
  );
}

