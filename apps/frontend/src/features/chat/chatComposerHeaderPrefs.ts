const KEY_PREFIX = "agent-layer.chat.composerHeaderCollapsed";

export function getChatComposerHeaderCollapsed(userId: string | null): boolean {
  if (!userId || typeof localStorage === "undefined") return true;
  const raw = localStorage.getItem(`${KEY_PREFIX}:${userId}`);
  if (raw === null) return true;
  return raw === "1";
}

export function setChatComposerHeaderCollapsed(userId: string | null, collapsed: boolean): void {
  if (!userId || typeof localStorage === "undefined") return;
  localStorage.setItem(`${KEY_PREFIX}:${userId}`, collapsed ? "1" : "0");
}
