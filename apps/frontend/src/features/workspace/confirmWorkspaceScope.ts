import { codingAgentPath } from "./codingWorkspaceNav";

/**
 * Ask whether to open an isolated Coding session instead of reusing the current thread.
 * Returns true if the caller should navigate to Coding (and stop in-place switch).
 */
export function confirmOpenCodingSessionForWorkspace(
  workspaceName: string,
  workspaceId: string
): boolean {
  const label = workspaceName.trim() || "this project";
  const ok = window.confirm(
    `Switching to "${label}" in this chat mixes context from different repositories.\n\n` +
      "OK — open a new Coding session for this project (recommended).\n" +
      "Cancel — change workspace in this thread anyway."
  );
  if (ok) {
    window.location.assign(codingAgentPath(workspaceId, { newSession: true }));
  }
  return ok;
}
