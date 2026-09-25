import { useTranslation } from "react-i18next";
import { Button } from "../../ui/Button";

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
    <div className="rounded-card border border-warning/40 bg-warning-subtle px-wide py-soft text-sm text-ink-primary">
      <p className="font-medium">
        {t("chat:permissionAskTitle", { tool: request.toolName })}
        {request.round != null ? (
          <span className="ml-base text-xs text-ink-muted">
            {t("chat:permissionAskRound", { round: request.round })}
          </span>
        ) : null}
      </p>
      {request.argsPreview ? (
        <pre className="mt-base max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-tile bg-black/30 p-base font-mono text-xs text-ink-muted">
          {request.argsPreview.slice(0, 1200)}
        </pre>
      ) : null}
      <div className="mt-soft flex flex-wrap gap-base">
        <button
          type="button"
          disabled={disabled}
          className="rounded-tile bg-warning px-soft py-snug text-xs font-medium text-black disabled:opacity-50"
          onClick={() => onReply("once")}
        >
          {t("chat:permissionAllowOnce")}
        </button>
        <button
          type="button"
          disabled={disabled}
          className="rounded-tile border border-line bg-black/20 px-soft py-snug text-xs text-ink-primary disabled:opacity-50"
          onClick={() => onReply("always")}
        >
          {t("chat:permissionAllowAlways")}
        </button>
        <Button
          type="button"
          variant="danger"
          size="sm"
          disabled={disabled}
          onClick={() => onReply("reject")}
        >
          {t("chat:permissionReject")}
        </Button>
      </div>
    </div>
  );
}
