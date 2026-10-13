import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatThread } from "../chat/chatThreadStorage";
import { Listbox } from "../../ui/Listbox";
import { Tooltip } from "../../ui/Tooltip";
import { useClickOutside } from "../../ui/useClickOutside";
import { Button } from "../../ui/Button";

type LabelPack = { shared: string; personal: string; untitled: string };

type Props = {
  threads: ChatThread[];
  activeThreadId: string | null;
  readOnly: boolean;
  disabled?: boolean;
  draftLabel: string;
  formatLabel: (row: ChatThread, labels: LabelPack) => string;
  onSelect: (conversationId: string) => void;
  triggerLabel: string;
};

export function DashboardEmbeddedThreadMenu({
  threads,
  activeThreadId,
  readOnly,
  disabled = false,
  draftLabel,
  formatLabel,
  onSelect,
  triggerLabel,
}: Props) {
  const { t } = useTranslation(["dashboard", "chat"]);
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useClickOutside(rootRef, () => setOpen(false), open);

  const labels: LabelPack = {
    shared: t("chat:visibilitySharedLabel"),
    personal: t("chat:visibilityPersonalLabel"),
    untitled: t("dashboard:embeddedChatUntitledThread"),
  };

  const canPick = !disabled && (threads.length > 0 || !readOnly);

  return (
    <div ref={rootRef} className="relative min-w-0 max-w-[58%]">
      <Tooltip label={t("dashboard:embeddedChatThreadMenuHint")}>
      <Button
        variant="plain"
        block
          type="button"
          disabled={!canPick}
          className="max-w-full items-center gap-hair truncate text-meta text-ink-secondary hover:text-white"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => {
            if (!canPick) return;
            setOpen((o) => !o);
          }}
      >
          <span className="truncate">{triggerLabel}</span>
          {canPick ? <span className="shrink-0 text-ink-muted">▾</span> : null}
        </Button>
      </Tooltip>
      {open ? (
        <Listbox
          id={menuId}
          ariaLabel={triggerLabel}
          className="absolute left-0 top-full z-docked mt-tight w-[min(280px,calc(100vw-2rem))]"
          value={activeThreadId ?? ""}
          onSelect={(next) => onSelect(next)}
          onClose={() => setOpen(false)}
          options={[
            // The draft is an entry in the list, not a special row above it: it
            // is one of the things you can be looking at, and it is selected
            // exactly when no thread is.
            ...(readOnly ? [] : [{ value: "", label: draftLabel }]),
            ...threads.map((row) => ({ value: row.id, label: formatLabel(row, labels) })),
          ]}
        />
      ) : null}
    </div>
  );
}
