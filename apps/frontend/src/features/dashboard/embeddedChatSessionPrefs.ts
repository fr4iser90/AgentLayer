const KEY_PREFIX = "agent-layer.dashboard.embeddedChat.sessionOpen";

export function getEmbeddedChatSessionOpen(
  userId: string | null | undefined,
  dashboardId: string
): boolean {
  if (!userId || !dashboardId || typeof localStorage === "undefined") return false;
  return localStorage.getItem(`${KEY_PREFIX}:${userId}:${dashboardId}`) === "1";
}

export function setEmbeddedChatSessionOpen(
  userId: string | null | undefined,
  dashboardId: string,
  open: boolean
): void {
  if (!userId || !dashboardId || typeof localStorage === "undefined") return;
  localStorage.setItem(`${KEY_PREFIX}:${userId}:${dashboardId}`, open ? "1" : "0");
}
