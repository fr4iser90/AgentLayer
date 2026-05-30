/** Deep-link into Chat scoped to one project workspace. */

export type ChatWorkspaceNavOptions = {
  /** Start a fresh chat for this workspace (recommended when changing repos). */
  newSession?: boolean;
};

export function chatWorkspacePath(workspaceId: string, options?: ChatWorkspaceNavOptions): string {
  const id = workspaceId.trim();
  const params = new URLSearchParams();
  params.set("workspace", id);
  if (options?.newSession) {
    params.set("new", "1");
  }
  return `/app/chat?${params.toString()}`;
}

/** @deprecated Use chatWorkspacePath — legacy name from removed Coding page. */
export function codingAgentPath(workspaceId: string, options?: ChatWorkspaceNavOptions): string {
  return chatWorkspacePath(workspaceId, options);
}

/** True when switching workspace would mix repo context in an existing thread. */
export function shouldIsolateWorkspaceThread(
  messageCount: number,
  previousWorkspaceId: string | null | undefined,
  nextWorkspaceId: string | null
): boolean {
  if (!nextWorkspaceId || messageCount <= 0) return false;
  if (!previousWorkspaceId || !previousWorkspaceId.trim()) return messageCount > 0;
  return previousWorkspaceId.trim() !== nextWorkspaceId.trim();
}
