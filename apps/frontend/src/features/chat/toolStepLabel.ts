/**
 * Display text for a tool step in run cards / activity.
 * Prefer ``step_label`` from the backend (built from plugin TOOL_LABEL + args).
 */

export function formatToolStepLabel(
  toolName: string | undefined,
  _summary: string | undefined,
  toolLabel?: string | undefined,
  stepLabel?: string | undefined,
): string {
  const ready = (stepLabel ?? "").trim();
  if (ready) return ready;

  const name = (toolName ?? "").trim();
  const verb = (toolLabel ?? "").trim() || (name ? name.replace(/_/g, " ") : "Tool");
  return verb;
}
