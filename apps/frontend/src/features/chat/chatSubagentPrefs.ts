const KEY_PREFIX = "agent-layer.chat.showSubagents";

export function getShowSubagentsInActivity(userId: string | null): boolean {
  if (!userId || typeof localStorage === "undefined") return true;
  const v = localStorage.getItem(`${KEY_PREFIX}:${userId}`);
  if (v === null) return true;
  return v === "1";
}

export function setShowSubagentsInActivity(userId: string | null, show: boolean): void {
  if (!userId || typeof localStorage === "undefined") return;
  localStorage.setItem(`${KEY_PREFIX}:${userId}`, show ? "1" : "0");
}
