import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import deCommon from "../locales/de/common.json";
import enCommon from "../locales/en/common.json";
import deAdmin from "../locales/de/admin.json";
import enAdmin from "../locales/en/admin.json";
import deAuth from "../locales/de/auth.json";
import enAuth from "../locales/en/auth.json";
import deChat from "../locales/de/chat.json";
import enChat from "../locales/en/chat.json";
import deCoding from "../locales/de/coding.json";
import enCoding from "../locales/en/coding.json";
import deDashboard from "../locales/de/dashboard.json";
import enDashboard from "../locales/en/dashboard.json";
import deErrors from "../locales/de/errors.json";
import enErrors from "../locales/en/errors.json";
import deSettings from "../locales/de/settings.json";
import enSettings from "../locales/en/settings.json";
import deSetup from "../locales/de/setup.json";
import enSetup from "../locales/en/setup.json";
import deTasks from "../locales/de/tasks.json";
import enTasks from "../locales/en/tasks.json";
import deWorkspace from "../locales/de/workspace.json";
import enWorkspace from "../locales/en/workspace.json";

const SUPPORTED = ["en", "de"] as const;

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        common: enCommon,
        errors: enErrors,
        chat: enChat,
        coding: enCoding,
        setup: enSetup,
        admin: enAdmin,
        auth: enAuth,
        settings: enSettings,
        tasks: enTasks,
        dashboard: enDashboard,
        workspace: enWorkspace,
      },
      de: {
        common: deCommon,
        errors: deErrors,
        chat: deChat,
        coding: deCoding,
        setup: deSetup,
        admin: deAdmin,
        auth: deAuth,
        settings: deSettings,
        tasks: deTasks,
        dashboard: deDashboard,
        workspace: deWorkspace,
      },
    },
    fallbackLng: "en",
    supportedLngs: [...SUPPORTED],
    defaultNS: "common",
    ns: ["common", "errors", "chat", "coding", "setup", "admin", "auth", "settings", "tasks", "dashboard", "workspace"],
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "agent-ui.lang",
    },
  });

export { SUPPORTED };
export default i18n;
