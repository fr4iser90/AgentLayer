/** Per-browser: show model reasoning/thinking in assistant chat bubbles. Default off. */

const STORAGE_KEY = "agentlayer.agent.show_reasoning";

export function getAgentShowReasoning(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return false;
    return raw === "1" || raw.toLowerCase() === "true";
  } catch {
    return false;
  }
}

export function setAgentShowReasoning(on: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
}
