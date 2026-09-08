import { useTranslation } from "react-i18next";

export type PermissionAskPayload = {
  requestId: string;
  toolName: string;
  argsPreview: string;
  round?: number | null;
};

type Props = {
  request: PermissionAskPayload;
  onReply: (reply: "once" | "always" | "reject") => void;
  disabled?: boolean;
};

export function PermissionAskCard({ request, onReply, disabled }: Props) {
  const { t } = useTranslation(["chat"]);
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-white">
      <p className="font-medium">
        {t("chat:permissionAskTitle", { tool: request.toolName })}
        {request.round != null ? (
          <span className="ml-2 text-xs text-surface-muted">
            {t("chat:permissionAskRound", { round: request.round })}
          </span>
        ) : null}
      </p>
      {request.argsPreview ? (
        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-all rounded bg-black/30 p-2 font-mono text-xs text-surface-muted">
          {request.argsPreview.slice(0, 1200)}
        </pre>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled}
          className="rounded-md bg-amber-500/90 px-3 py-1.5 text-xs font-medium text-black disabled:opacity-50"
          onClick={() => onReply("once")}
        >
          {t("chat:permissionAllowOnce")}
        </button>
        <button
          type="button"
          disabled={disabled}
          className="rounded-md border border-surface-border bg-black/20 px-3 py-1.5 text-xs text-white disabled:opacity-50"
          onClick={() => onReply("always")}
        >
          {t("chat:permissionAllowAlways")}
        </button>
        <button
          type="button"
          disabled={disabled}
          className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs text-red-200 disabled:opacity-50"
          onClick={() => onReply("reject")}
        >
          {t("chat:permissionReject")}
        </button>
      </div>
    </div>
  );
}
