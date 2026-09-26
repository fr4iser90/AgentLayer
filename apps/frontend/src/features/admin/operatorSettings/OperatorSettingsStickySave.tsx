import { useTranslation } from "react-i18next";
import { StickySaveBar } from "../../../ui/StickySaveBar";
import { useOperatorSettings } from "./OperatorSettingsProvider";

export function OperatorSettingsStickySave() {
  const { t } = useTranslation(["admin"]);
  const { save, saveMsg } = useOperatorSettings();
  return (
    <StickySaveBar
      saveLabel={t("admin:save")}
      onSave={() => void save()}
      status={saveMsg ? { ok: saveMsg.ok, text: saveMsg.text } : null}
    >
      <span>{t("admin:operatorSaveHint")}</span>
    </StickySaveBar>
  );
}
