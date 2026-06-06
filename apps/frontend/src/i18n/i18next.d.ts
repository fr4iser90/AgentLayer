import "i18next";

import type common from "../locales/en/common.json";
import type errors from "../locales/en/errors.json";
import type chat from "../locales/en/chat.json";
import type coding from "../locales/en/coding.json";
import type setup from "../locales/en/setup.json";
import type admin from "../locales/en/admin.json";
import type auth from "../locales/en/auth.json";
import type settings from "../locales/en/settings.json";
import type tasks from "../locales/en/tasks.json";
import type dashboard from "../locales/en/dashboard.json";
import type notifications from "../locales/en/notifications.json";
import type workspace from "../locales/en/workspace.json";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: {
      common: typeof common;
      errors: typeof errors;
      chat: typeof chat;
      coding: typeof coding;
      setup: typeof setup;
      admin: typeof admin;
      auth: typeof auth;
      settings: typeof settings;
      tasks: typeof tasks;
      dashboard: typeof dashboard;
      notifications: typeof notifications;
      workspace: typeof workspace;
    };
  }
}
