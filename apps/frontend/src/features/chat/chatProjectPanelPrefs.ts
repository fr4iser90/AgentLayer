const KEY_PREFIX = "agent-layer.chat.projectPanelOpen";

export function getChatProjectPanelOpen(userId: string | null): boolean {
  if (!userId || typeof localStorage === "undefined") return false;
  return localStorage.getItem(`${KEY_PREFIX}:${userId}`) === "1";
}

export function setChatProjectPanelOpen(userId: string | null, open: boolean): void {
  if (!userId || typeof localStorage === "undefined") return;
  localStorage.setItem(`${KEY_PREFIX}:${userId}`, open ? "1" : "0");
}
