import { useTranslation } from "react-i18next";
import type { UiMessage } from "./chatThreadStorage";
import { parseContentParts } from "./messageFormat";

type Part = { type?: string; text?: string; image_url?: { url?: string } };

function MessageBody({ content }: { content: string }) {
  const { plain, parts } = parseContentParts(content);
  if (parts) {
    return (
      <div className="space-y-2">
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
                className="max-h-64 max-w-full rounded-md border border-white/10 object-contain"
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
    <div className="group relative max-w-[min(100%,42rem)] rounded-2xl border border-sky-900/40 bg-[#1a2a3d] px-4 py-3 text-sm text-neutral-100 shadow-sm">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wide text-surface-muted">
          {t("chat:roleYou")}
          {timeLabel ? (
            <span className="ml-2 font-normal normal-case">{timeLabel}</span>
          ) : null}
        </span>
        <div className="flex shrink-0 items-center gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
          <button
            type="button"
            onClick={onCopy}
            className="rounded-md px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sky-200/80 hover:bg-white/10 hover:text-sky-100"
            title={t("chat:messageCopyTitle")}
          >
            {t("chat:messageCopy")}
          </button>
          {showRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="rounded-md px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-violet-200/80 hover:bg-white/10 hover:text-violet-100"
              title={t("chat:messageRetryTitle")}
            >
              {t("chat:messageRetry")}
            </button>
          ) : null}
        </div>
      </div>
      <MessageBody content={message.content} />
    </div>
  );
}
