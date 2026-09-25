import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { ThumbsDown, ThumbsUp } from "lucide-react";
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
    <div className="mt-base flex items-center gap-tight border-t border-line-subtle pt-base">
      <span className="mr-tight text-meta text-ink-muted">{t("chat:feedbackPrompt")}</span>
      <button
        type="button"
        disabled={busy}
        aria-pressed={rating === "up"}
        aria-label={t("chat:feedbackUp")}
        className={[
          "rounded-tile px-snug py-hair text-sm transition-colors",
          rating === "up"
            ? "bg-success-subtle text-badge-success"
            : "text-ink-muted hover:bg-white/5 hover:text-neutral-300",
        ].join(" ")}
        onClick={() => void submit("up")}
      >
        <ThumbsUp aria-hidden className="h-4 w-4" />
      </button>
      <button
        type="button"
        disabled={busy}
        aria-pressed={rating === "down"}
        aria-label={t("chat:feedbackDown")}
        className={[
          "rounded-tile px-snug py-hair text-sm transition-colors",
          rating === "down"
            ? "bg-danger-subtle text-badge-danger"
            : "text-ink-muted hover:bg-white/5 hover:text-neutral-300",
        ].join(" ")}
        onClick={() => void submit("down")}
      >
        <ThumbsDown aria-hidden className="h-4 w-4" />
      </button>
    </div>
  );
}
