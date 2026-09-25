import i18n from "i18next";
import { toast } from "../../ui/toastBus";
import type { AuthContextValue } from "../../auth/AuthContext";
import type { ChatThread } from "./chatThreadStorage";
import { putConversation } from "./conversationsApi";

type SaveAuth = Pick<AuthContextValue, "accessToken" | "refresh">;

/**
 * What happens when a chat save fails.
 *
 * Nine `putConversation()` calls in `ChatPage` ended in `.catch(() => {})`.
 * The user's message goes into local state and renders immediately, so the
 * transcript looks saved; the server never got it; a reload deletes it. Nothing
 * anywhere said so — the quietest data loss in the app, and the one that
 * destroys trust in the transcript rather than in a feature.
 *
 * One toast per failure streak, not one per call: a network that is down
 * produces a failure on every keystroke-driven save, and a wall of identical
 * toasts hides the message instead of delivering it. The retry re-runs the save
 * that actually failed, with the thread as it stands now.
 */
const SAVE_KEY = "chat:save-failed";

export function reportChatSaveFailure(retry: () => void): void {
  console.error("[chat] conversation save failed — the transcript is ahead of the server");
  toast.once(
    SAVE_KEY,
    (onRetry) => ({
      title: i18n.t("chat:saveFailedTitle"),
      body: i18n.t("chat:saveFailedBody"),
      tone: "danger",
      durationMs: null,
      action: { label: i18n.t("chat:saveRetry"), onClick: onRetry },
    }),
    retry
  );
}

/** A later save succeeded, so the warning is no longer true. */
export function settleChatSaveFailure(): void {
  toast.settle(SAVE_KEY);
}

/**
 * The activity log is a different class: losing it costs the trace, not the
 * user's words. It stays out of the UI and into the console — silent, but never
 * without a reason.
 */
export function reportAgentLogFailure(error: unknown): void {
  console.warn("[chat] agent activity log save failed", error);
}

/**
 * A delegate toggle that the server refused.
 *
 * The control keeps showing what the user clicked, which is now the honest
 * complaint: the message says the write did not land. Reverting the control is
 * the better behaviour and needs the previous value threaded back into each
 * call site — a separate change, not something to smuggle into this one.
 */
export function reportDelegatePrefFailure(error: unknown): void {
  console.error("[chat] delegate preference save failed", error);
  toast.once("chat:delegate-pref-failed", () => ({
    title: i18n.t("chat:delegatePrefSaveFailedTitle"),
    body: i18n.t("chat:delegatePrefSaveFailedBody"),
    tone: "warning",
  }));
}

/**
 * Save a thread and report if it did not land.
 *
 * Replaces `void putConversation(auth, th).catch(() => {})`. The retry re-PUTs
 * the same thread snapshot: a newer save has already made its own call with
 * newer content, so replaying the old one cannot overwrite it with anything
 * staler than what the failed attempt would have written.
 */
export function saveConversation(auth: SaveAuth, thread: ChatThread): Promise<void> {
  return putConversation(auth, thread)
    .then(() => {
      settleChatSaveFailure();
    })
    .catch(() => {
      reportChatSaveFailure(() => {
        void saveConversation(auth, thread);
      });
    });
}