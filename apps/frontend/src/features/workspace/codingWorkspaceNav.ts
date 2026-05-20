/** Deep-link into Coding Agent scoped to one project workspace. */

export type CodingAgentNavOptions = {
  /** Start a fresh coding conversation for this workspace (recommended when changing repos). */
  newSession?: boolean;
};

export function codingAgentPath(workspaceId: string, options?: CodingAgentNavOptions): string {
  const id = workspaceId.trim();
  const params = new URLSearchParams();
  params.set("workspace", id);
  if (options?.newSession) {
    params.set("new", "1");
  }
  // SPA is mounted at /app (see App.tsx basename); bare /coding-agent hits API auth → 401 JSON.
  return `/app/coding-agent?${params.toString()}`;
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
