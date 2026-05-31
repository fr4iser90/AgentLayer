import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type Props = {
  auth: AuthContextValue;
  conversationId: string | null | undefined;
  messagePosition: number;
  initialRating?: "up" | "down" | null;
};

export function MessageFeedbackButtons({
  auth,
  conversationId,
  messagePosition,
  initialRating = null,
}: Props) {
  const { t } = useTranslation(["chat"]);
  const [rating, setRating] = useState<"up" | "down" | null>(initialRating);
  const [busy, setBusy] = useState(false);

  const submit = useCallback(
    async (next: "up" | "down") => {
      if (!conversationId || !auth.accessToken || busy) return;
      const toggled = rating === next ? null : next;
      setBusy(true);
      try {
        if (toggled === null) {
          setRating(null);
          return;
        }
        const r = await apiFetch(
          `/v1/user/conversations/${encodeURIComponent(conversationId)}/feedback`,
          auth,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message_position: messagePosition,
              rating: toggled,
            }),
          }
        );
        if (!r.ok) throw new Error("feedback failed");
        setRating(toggled);
      } catch {
        /* keep prior state */
      } finally {
        setBusy(false);
      }
    },
    [auth, busy, conversationId, messagePosition, rating]
  );

  if (!conversationId) return null;

  return (
    <div className="mt-2 flex items-center gap-1 border-t border-white/5 pt-2">
      <span className="mr-1 text-[10px] text-surface-muted">{t("chat:feedbackPrompt")}</span>
      <button
        type="button"
        disabled={busy}
        aria-pressed={rating === "up"}
        aria-label={t("chat:feedbackUp")}
        className={[
          "rounded px-1.5 py-0.5 text-sm transition-colors",
          rating === "up"
            ? "bg-emerald-900/50 text-emerald-300"
            : "text-neutral-500 hover:bg-white/5 hover:text-neutral-300",
        ].join(" ")}
        onClick={() => void submit("up")}
      >
        👍
      </button>
      <button
        type="button"
        disabled={busy}
        aria-pressed={rating === "down"}
        aria-label={t("chat:feedbackDown")}
        className={[
          "rounded px-1.5 py-0.5 text-sm transition-colors",
          rating === "down"
            ? "bg-red-900/40 text-red-300"
            : "text-neutral-500 hover:bg-white/5 hover:text-neutral-300",
        ].join(" ")}
        onClick={() => void submit("down")}
      >
        👎
      </button>
    </div>
  );
}
