import i18n from "../../i18n/config";

/**
 * Ask whether to start a new chat instead of reusing the current thread when switching project.
 * Returns true if the caller should open a new chat (and stop in-place switch).
 */
export function confirmNewChatForWorkspace(workspaceName: string): boolean {
  const label = workspaceName.trim() || i18n.t("chat:projectFallbackName");
  return window.confirm(
    `${i18n.t("chat:workspaceSwitchConfirmIntro", { name: label })}\n\n` +
      `${i18n.t("chat:workspaceSwitchConfirmOk")}\n` +
      `${i18n.t("chat:workspaceSwitchConfirmCancel")}`
  );
}

/** @deprecated */
export const confirmOpenCodingSessionForWorkspace = confirmNewChatForWorkspace;
