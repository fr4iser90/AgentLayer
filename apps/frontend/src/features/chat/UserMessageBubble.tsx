import { useTranslation } from "react-i18next";
import type { UiMessage } from "./chatThreadStorage";
import { parseContentParts } from "./messageFormat";
import { Tooltip } from "../../ui/Tooltip";
import { Button } from "../../ui/Button";

type Part = { type?: string; text?: string; image_url?: { url?: string } };

function MessageBody({ content }: { content: string }) {
  const { plain, parts } = parseContentParts(content);
  if (parts) {
    return (
      <div className="space-y-base">
        {parts.map((p, i) => {
          if (p.type === "text" && p.text) {
            return (
              <div key={i} className="whitespace-pre-wrap">
                {p.text}
              </div>
            );
          }
          if (p.type === "image_url" && p.image_url?.url) {
            return (
              <img
                key={i}
                src={p.image_url.url}
                alt=""
                className="max-h-64 max-w-full rounded-tile border border-line object-contain"
              />
            );
          }
          return null;
        })}
      </div>
    );
  }
  return <div className="whitespace-pre-wrap">{plain}</div>;
}

type Props = {
  message: UiMessage;
  timeLabel: string | null;
  showRetry: boolean;
  onCopy: () => void;
  onRetry: () => void;
};

export function UserMessageBubble({ message, timeLabel, showRetry, onCopy, onRetry }: Props) {
  const { t } = useTranslation(["chat"]);

  return (
    <div className="group relative max-w-measure rounded-sheet border border-accent/40 bg-[#1a2a3d] px-wide py-soft text-sm text-ink-primary shadow-sm">
      <div className="mb-tight flex items-center justify-between gap-base">
        <span className="text-meta font-medium uppercase tracking-wide text-ink-muted">
          {t("chat:roleYou")}
          {timeLabel ? (
            <span className="ml-base font-normal normal-case">{timeLabel}</span>
          ) : null}
        </span>
        <div className="flex shrink-0 items-center gap-tight opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
          <Tooltip label={t("chat:messageCopyTitle")}>
          <Button
            variant="ghost"
              type="button"
              onClick={onCopy}
              className="px-base py-hair text-meta uppercase tracking-wide text-badge-accent hover:bg-white/10 hover:text-badge-accent"
          >
              {t("chat:messageCopy")}
            </Button>
          </Tooltip>
          {showRetry ? (
            <Tooltip label={t("chat:messageRetryTitle")}>
            <Button
              variant="ghost"
                type="button"
                onClick={onRetry}
                className="px-base py-hair text-meta uppercase tracking-wide text-violet-200/80 hover:bg-white/10 hover:text-violet-100"
            >
                {t("chat:messageRetry")}
              </Button>
            </Tooltip>
          ) : null}
        </div>
      </div>
      <MessageBody content={message.content} />
    </div>
  );
}
