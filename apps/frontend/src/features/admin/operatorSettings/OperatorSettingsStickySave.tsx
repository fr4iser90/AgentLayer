import { useTranslation } from "react-i18next";
import { useOperatorSettings } from "./OperatorSettingsProvider";

export function OperatorSettingsStickySave() {
  const { t } = useTranslation(["admin"]);
  const { save, saveMsg } = useOperatorSettings();
  return (
    <div className="sticky bottom-0 z-10 -mx-6 border-t border-surface-border bg-[#0d0d0d]/95 px-6 py-3 backdrop-blur-sm">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1 text-xs text-surface-muted">
          {saveMsg ? (
            <span className={saveMsg.ok ? "text-emerald-400" : "text-red-400"}>{saveMsg.text}</span>
          ) : (
            <span>{t("admin:operatorSaveHint")}</span>
          )}
        </div>
        <button
          type="button"
          className="shrink-0 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
          onClick={() => void save()}
        >
          {t("admin:save")}
        </button>
      </div>
    </div>
  );
}
