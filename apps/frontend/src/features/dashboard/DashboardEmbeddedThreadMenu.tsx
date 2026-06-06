import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ChatThread } from "../chat/chatThreadStorage";

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

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const labels: LabelPack = {
    shared: t("chat:visibilitySharedLabel"),
    personal: t("chat:visibilityPersonalLabel"),
    untitled: t("dashboard:embeddedChatUntitledThread"),
  };

  const canPick = !disabled && (threads.length > 0 || !readOnly);

  return (
    <div ref={rootRef} className="relative min-w-0 max-w-[58%]">
      <button
        type="button"
        disabled={!canPick}
        className="flex max-w-full items-center gap-0.5 truncate text-left text-[10px] text-neutral-300 hover:text-white disabled:opacity-50"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={menuId}
        title={t("dashboard:embeddedChatThreadMenuHint")}
        onClick={() => {
          if (!canPick) return;
          setOpen((o) => !o);
        }}
      >
        <span className="truncate">{triggerLabel}</span>
        {canPick ? <span className="shrink-0 text-surface-muted">▾</span> : null}
      </button>
      {open ? (
        <ul
          id={menuId}
          role="listbox"
          className="absolute left-0 top-full z-30 mt-1 max-h-[min(240px,40vh)] w-[min(280px,calc(100vw-2rem))] overflow-y-auto rounded-lg border border-surface-border bg-[#141414] py-1 shadow-xl"
        >
          {!readOnly ? (
            <li role="option" aria-selected={!activeThreadId}>
              <button
                type="button"
                className={[
                  "w-full px-3 py-2 text-left text-xs hover:bg-white/5",
                  !activeThreadId ? "bg-sky-950/40 text-sky-100" : "text-neutral-200",
                ].join(" ")}
                onClick={() => {
                  onSelect("");
                  setOpen(false);
                }}
              >
                {draftLabel}
              </button>
            </li>
          ) : null}
          {threads.map((row) => {
            const selected = activeThreadId === row.id;
            return (
              <li key={row.id} role="option" aria-selected={selected}>
                <button
                  type="button"
                  className={[
                    "w-full px-3 py-2 text-left text-xs hover:bg-white/5",
                    selected ? "bg-sky-950/40 text-sky-100" : "text-neutral-200",
                  ].join(" ")}
                  onClick={() => {
                    onSelect(row.id);
                    setOpen(false);
                  }}
                >
                  <span className="line-clamp-2">{formatLabel(row, labels)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
