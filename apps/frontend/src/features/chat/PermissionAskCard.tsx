import { useTranslation } from "react-i18next";
import { ActionCard } from "../../ui/ActionCard";
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
    <ActionCard
      tone="warning"
      title={t("chat:permissionAskTitle", { tool: request.toolName })}
      reason={t("chat:permissionAskIntro")}
      badge={
        request.round != null
          ? { label: t("chat:permissionAskRound", { round: request.round }) }
          : undefined
      }
      primary={
        <Button
          variant="primary"
          tone="warning"
          size="sm"
          type="button"
          disabled={disabled}
          onClick={() => onReply("once")}
        >
          {t("chat:permissionAllowOnce")}
        </Button>
      }
      secondary={
        <>
          <Button size="sm" type="button" disabled={disabled} onClick={() => onReply("always")}>
            {t("chat:permissionAllowAlways")}
          </Button>
          <Button
            type="button"
            variant="danger"
            size="sm"
            disabled={disabled}
            onClick={() => onReply("reject")}
          >
            {t("chat:permissionReject")}
          </Button>
        </>
      }
    >
      {request.argsPreview ? (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-tile bg-black/30 p-base font-mono text-xs text-ink-muted">
          {request.argsPreview.slice(0, 1200)}
        </pre>
      ) : null}
    </ActionCard>
  );
}
