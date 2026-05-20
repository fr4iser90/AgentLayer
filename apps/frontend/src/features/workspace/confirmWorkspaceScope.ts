/**
 * Ask whether to start a new chat instead of reusing the current thread when switching project.
 * Returns true if the caller should open a new chat (and stop in-place switch).
 */
export function confirmOpenCodingSessionForWorkspace(
  workspaceName: string,
  _workspaceId: string
): boolean {
  const label = workspaceName.trim() || "this project";
  return window.confirm(
    `Switching to "${label}" in this chat mixes context from different repositories.\n\n` +
      "OK — start a new chat for this project (recommended).\n" +
      "Cancel — change workspace in this thread anyway."
  );
}
