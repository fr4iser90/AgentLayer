/** Minimal WebSocket agent turn for dashboard embedded chat (tools enabled). */

function wsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/v1/chat?token=${encodeURIComponent(token)}`;
}

function assistantFromCompletion(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const d = data as { choices?: Array<{ message?: { content?: unknown } }> };
  const c = d.choices?.[0]?.message?.content;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    return c
      .map((part: unknown) => {
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text?: string }).text ?? "");
        }
        return "";
      })
      .join("");
  }
  return "";
}

export type DashboardAgentToolDone = {
  name: string;
  proposalSetId?: string;
  dashboardId?: string;
  ok?: boolean;
};

export type RunDashboardAgentTurnOpts = {
  accessToken: string;
  model: string;
  provider: string | null | undefined;
  messages: Array<{ role: string; content: unknown }>;
  dashboardId: string;
  /** Pinned block for agent context (patch_layout / set_props). */
  focusedBlockId?: string | null;
  conversationId?: string;
  disabledTools?: string[];
  /** Abort the turn if the LLM does not finish within this window (default 5 min). */
  timeoutMs?: number;
  onDelta?: (text: string) => void;
  onToolDone?: (ev: DashboardAgentToolDone) => void;
  onSlow?: (elapsedMs: number) => void;
};

export function runDashboardAgentTurn(opts: RunDashboardAgentTurnOpts): Promise<string> {
  const {
    accessToken,
    model,
    provider,
    messages,
    dashboardId,
    focusedBlockId,
    conversationId,
    disabledTools = [],
    timeoutMs = 300_000,
    onDelta,
    onToolDone,
    onSlow,
  } = opts;

  return new Promise((resolve, reject) => {
    let stream = "";
    let finished = false;
    const started = Date.now();
    const ws = new WebSocket(wsUrl(accessToken));
    const slowTimer = window.setTimeout(() => {
      if (!finished) onSlow?.(Date.now() - started);
    }, 90_000);
    const hardTimer = window.setTimeout(() => {
      if (!finished) fail("Agent turn timed out — the language model may still be generating. Try again.");
    }, Math.max(30_000, timeoutMs));

    const clearTimers = () => {
      window.clearTimeout(slowTimer);
      window.clearTimeout(hardTimer);
    };

    const finish = (content: string) => {
      if (finished) return;
      finished = true;
      clearTimers();
      try {
        ws.close();
      } catch {
        /* */
      }
      resolve(content);
    };

    const fail = (msg: string) => {
      if (finished) return;
      finished = true;
      clearTimers();
      try {
        ws.close();
      } catch {
        /* */
      }
      reject(new Error(msg));
    };

    ws.onerror = () => fail("WebSocket failed");
    ws.onclose = () => {
      if (!finished) fail("WebSocket closed");
    };

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: "chat",
          body: {
            model,
            messages,
            agent_id: "dashboard",
            agent_stream_llm: true,
            agent_dashboard_context: {
              dashboard_id: dashboardId,
              ...(focusedBlockId?.trim() ? { block_id: focusedBlockId.trim() } : {}),
            },
            ...(conversationId ? { conversation_id: conversationId } : {}),
            ...(disabledTools.length ? { agent_disabled_tools: disabledTools } : {}),
            agent_model_catalog_owned_by: provider ?? undefined,
          },
        })
      );
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        const typ = typeof msg.type === "string" ? msg.type : String(msg.type ?? "");
        if (typ === "pong") return;
        if (typ === "error") {
          fail(typeof msg.detail === "string" ? msg.detail : "Agent error");
          return;
        }
        if (typ === "agent.llm_delta") {
          const d = msg.delta != null ? String(msg.delta) : "";
          if (d) {
            stream += d;
            onDelta?.(stream);
          }
          return;
        }
        if (typ === "agent.tool_done") {
          const name = msg.name != null ? String(msg.name) : "tool";
          const proposalSetId =
            typeof msg.proposal_set_id === "string" ? msg.proposal_set_id : undefined;
          const dashId =
            typeof msg.dashboard_id === "string" ? msg.dashboard_id : undefined;
          const ok =
            msg.result_ok === false ? false : msg.result_ok === true ? true : undefined;
          onToolDone?.({ name, proposalSetId, dashboardId: dashId, ok });
          return;
        }
        if (typ === "chat.completion") {
          if (msg.error) {
            fail(typeof msg.detail === "string" ? msg.detail : "Agent turn failed");
            return;
          }
          const fromApi = assistantFromCompletion(msg.data);
          const content = stream.trim() || fromApi.trim() || "(empty)";
          finish(content);
          return;
        }
        if (typ === "agent.aborted" || typ === "agent.cancelled") {
          fail(typeof msg.detail === "string" ? msg.detail : "Agent cancelled");
        }
      } catch {
        fail("Invalid WebSocket message");
      }
    };
  });
}
