import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

export async function fetchConversationFeedback(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  conversationId: string
): Promise<Map<number, "up" | "down">> {
  const r = await apiFetch(
    `/v1/user/conversations/${encodeURIComponent(conversationId)}/feedback`,
    auth
  );
  if (!r.ok) return new Map();
  const data = (await r.json()) as {
    feedback?: Array<{ message_position?: number; rating?: number }>;
  };
  const out = new Map<number, "up" | "down">();
  for (const row of data.feedback ?? []) {
    const pos = row.message_position;
    if (typeof pos !== "number") continue;
    out.set(pos, row.rating === 1 ? "up" : "down");
  }
  return out;
}

export async function patchDelegatePrefs(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  conversationId: string,
  body: {
    delegate_auto_respond_enabled?: boolean;
    delegate_auto_respond_after_sec?: number;
    delegate_max_chain_turns?: number;
  }
): Promise<void> {
  const r = await apiFetch(
    `/v1/user/conversations/${encodeURIComponent(conversationId)}/delegate-prefs`,
    auth,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  if (!r.ok) {
    const data = (await r.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(typeof data.detail === "string" ? data.detail : "delegate prefs failed");
  }
}

export type DelegateRespondResult = {
  synthetic_user_message: string;
  decision_summary?: string;
  stand_in_marker?: string;
  delegate_run_id?: string;
};

export async function postDelegateRespond(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  conversationId: string
): Promise<DelegateRespondResult> {
  const r = await apiFetch(
    `/v1/user/conversations/${encodeURIComponent(conversationId)}/delegate-respond`,
    auth,
    { method: "POST" }
  );
  const data = (await r.json()) as DelegateRespondResult & { detail?: string };
  if (!r.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "delegate respond failed");
  }
  return data;
}
