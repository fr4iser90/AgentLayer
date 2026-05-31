import { useEffect, useRef } from "react";
import type { AuthContextValue } from "../../auth/AuthContext";
import type { ChatThread } from "./chatThreadStorage";
import { patchDelegatePrefs, postDelegateRespond } from "./chatExtrasApi";
import { newMessageId } from "./chatThreadStorage";

type Args = {
  auth: AuthContextValue;
  activeThread: ChatThread | null;
  loading: boolean;
  mode: "chat" | "agent";
  draft: string;
  onAgentDone: () => void;
  onSyntheticTurn: (userContent: string, standIn: boolean) => void;
};

export function useDelegateAutoRespond({
  auth,
  activeThread,
  loading,
  mode,
  draft,
  onAgentDone,
  onSyntheticTurn,
}: Args) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firingRef = useRef(false);
  const draftRef = useRef(draft);
  draftRef.current = draft;

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => clearTimer, [activeThread?.id]);

  useEffect(() => {
    if (draft.trim()) clearTimer();
  }, [draft]);

  const scheduleAfterDone = () => {
    clearTimer();
    const thread = activeThread;
    if (!thread?.id || !thread.delegateAutoRespondEnabled) return;
    if (mode !== "agent" || loading) return;
    const sec = Math.max(15, Math.min(thread.delegateAutoRespondAfterSec ?? 60, 600));
    timerRef.current = setTimeout(() => {
      void (async () => {
        if (firingRef.current || loading || draftRef.current.trim()) return;
        if (!thread.id) return;
        firingRef.current = true;
        try {
          const res = await postDelegateRespond(auth, thread.id);
          const marker = res.stand_in_marker ?? "[Stand-in · auto]";
          const body = `${marker}\n${res.synthetic_user_message}`.trim();
          onSyntheticTurn(body, true);
        } catch {
          /* escalate / limit — silent */
        } finally {
          firingRef.current = false;
        }
      })();
    }, sec * 1000);
  };

  return {
    clearTimer,
    scheduleAfterDone,
    setEnabled: async (enabled: boolean) => {
      const id = activeThread?.id;
      if (!id) return;
      await patchDelegatePrefs(auth, id, { delegate_auto_respond_enabled: enabled });
    },
    setDelaySec: async (sec: number) => {
      const id = activeThread?.id;
      if (!id) return;
      await patchDelegatePrefs(auth, id, {
        delegate_auto_respond_after_sec: Math.max(15, Math.min(sec, 600)),
      });
    },
    newSyntheticUserId: newMessageId,
    onAgentDone: () => {
      onAgentDone();
      scheduleAfterDone();
    },
  };
}
