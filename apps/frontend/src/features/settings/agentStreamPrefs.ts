/** Per-browser: stream LLM tokens over WebSocket agent rounds (``agent_stream_llm``). Default off. */

const STORAGE_KEY = "agentlayer.agent.stream_llm";

export function getAgentStreamLlm(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return false;
    return raw === "1" || raw.toLowerCase() === "true";
  } catch {
    return false;
  }
}

export function setAgentStreamLlm(on: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
}
