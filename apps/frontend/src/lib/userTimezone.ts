/** IANA timezone from the user's browser (per device/session). */
export function detectUserTimezone(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (typeof tz === "string" && tz.trim()) return tz.trim();
  } catch {
    /* ignore */
  }
  return "UTC";
}

export const USER_TIMEZONE_HEADER = "X-User-Timezone";
