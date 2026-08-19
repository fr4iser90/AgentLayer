import { useEffect, type Dispatch, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import { blockExpandTitle } from "./blockRegistry";
import { DashboardBlockTile } from "./DashboardBlocks";
import type { UiBlock } from "./types";

export function BlockExpandModal(props: {
  block: UiBlock;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  readOnly: boolean;
  interactOnly?: boolean;
  dashboardId: string | null;
  onClose: () => void;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { block, data, setData, readOnly, interactOnly = false, dashboardId, onClose } = props;
  const title = blockExpandTitle(block, t);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col bg-neutral-950/98"
      role="dialog"
      aria-modal="true"
      aria-label={t("dashboard:blockExpandDialogLabel", { title })}
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4 py-3 sm:px-6">
        <h2 className="min-w-0 truncate text-sm font-medium text-white sm:text-base">{title}</h2>
        <button
          type="button"
          className="shrink-0 rounded-lg bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/20"
          onClick={onClose}
        >
          {t("dashboard:blockExpandClose")}
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain p-4 sm:p-6">
        <div className="mx-auto max-w-6xl rounded-xl border border-surface-border bg-surface-raised/90 p-3 sm:p-4">
          <DashboardBlockTile
            block={block}
            data={data}
            setData={setData}
            readOnly={readOnly}
            interactOnly={interactOnly}
            dashboardId={dashboardId}
            displayMode="expanded"
          />
        </div>
      </div>
    </div>
  );
}
