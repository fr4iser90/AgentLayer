import type { Dispatch, SetStateAction } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTranslation } from "react-i18next";

import { getPath, setPath } from "./dashboardDataPaths";

function newKanbanId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

type KanbanCard = { id: string; title: string };
type KanbanColumn = { id: string; title: string; cards: KanbanCard[] };

function readKanban(raw: unknown): { columns: KanbanColumn[] } {
  const defaultColTitle = "Spalte";
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return { columns: [] };
  }
  const o = raw as Record<string, unknown>;
  const cols = Array.isArray(o.columns) ? o.columns : [];
  return {
    columns: cols.map((c, i) => {
      const col = c && typeof c === "object" && !Array.isArray(c) ? (c as Record<string, unknown>) : {};
      const cardsRaw = Array.isArray(col.cards) ? col.cards : [];
      const cards: KanbanCard[] = cardsRaw.map((k, j) => {
        const card = k && typeof k === "object" && !Array.isArray(k) ? (k as Record<string, unknown>) : {};
        return {
          id: String(card.id || `card_${j}`),
          title: String(card.title ?? ""),
        };
      });
      return {
        id: String(col.id || `col_${i}`),
        title: String(col.title || defaultColTitle),
        cards,
      };
    }),
  };
}

export function KanbanBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  readOnly: boolean;
  displayMode?: "grid" | "expanded";
}) {
  const { t } = useTranslation(["dashboard"]);
  const { dp, data, setData, sectionTitle, readOnly, displayMode = "grid" } = props;
  const { columns } = readKanban(dp ? getPath(data, dp) : undefined);

  const write = (next: { columns: KanbanColumn[] }) => {
    setData((d) => setPath(d, dp, next as unknown));
  };

  const updateColTitle = (ci: number, title: string) => {
    const next = { columns: columns.map((c, i) => (i === ci ? { ...c, title } : c)) };
    write(next);
  };

  const addColumn = () => {
    write({
      columns: [
        ...columns,
        { id: newKanbanId("col"), title: t("dashboard:kanbanNewColumnTitle"), cards: [] },
      ],
    });
  };

  const removeColumn = (ci: number) => {
    if (columns.length <= 1) return;
    write({ columns: columns.filter((_, i) => i !== ci) });
  };

  const addCard = (ci: number) => {
    const next = columns.map((c, i) =>
      i === ci
        ? { ...c, cards: [...c.cards, { id: newKanbanId("card"), title: "" }] }
        : c
    );
    write({ columns: next });
  };

  const updateCardTitle = (ci: number, cardId: string, title: string) => {
    const next = columns.map((c, i) => {
      if (i !== ci) return c;
      return {
        ...c,
        cards: c.cards.map((k) => (k.id === cardId ? { ...k, title } : k)),
      };
    });
    write({ columns: next });
  };

  const removeCard = (ci: number, cardId: string) => {
    const next = columns.map((c, i) =>
      i === ci ? { ...c, cards: c.cards.filter((k) => k.id !== cardId) } : c
    );
    write({ columns: next });
  };

  const moveCard = (fromCi: number, cardId: string, toCi: number) => {
    if (fromCi === toCi) return;
    let card: KanbanCard | null = null;
    const stripped = columns.map((c, i) => {
      if (i !== fromCi) return c;
      const cards = c.cards.filter((k) => {
        if (k.id === cardId) {
          card = k;
          return false;
        }
        return true;
      });
      return { ...c, cards };
    });
    if (!card) return;
    const withTarget = stripped.map((c, i) =>
      i === toCi ? { ...c, cards: [...c.cards, card!] } : c
    );
    write({ columns: withTarget });
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-3 md:p-4">
      {displayMode === "grid" ? (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-white">{sectionTitle}</h3>
          {!readOnly ? (
            <button
              type="button"
              className="rounded-md bg-sky-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={addColumn}
            >
              {t("dashboard:kanbanAddColumn")}
            </button>
          ) : null}
        </div>
      ) : (
        !readOnly ? (
          <div className="mb-3 flex justify-end">
            <button
              type="button"
              className="rounded-md bg-sky-600/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
              onClick={addColumn}
            >
              {t("dashboard:kanbanAddColumn")}
            </button>
          </div>
        ) : null
      )}
      <div
        className={[
          "flex gap-3 overflow-x-auto pb-1",
          displayMode === "expanded" ? "min-h-[min(60vh,520px)]" : "min-h-[120px]",
        ].join(" ")}
      >
        {columns.map((col, ci) => (
          <div
            key={col.id}
            className="flex w-[min(100%,280px)] shrink-0 flex-col rounded-lg border border-white/10 bg-black/25 p-2"
          >
            <div className="mb-2 flex items-center gap-1">
              {readOnly ? (
                <span className="flex-1 truncate text-sm font-medium text-white">{col.title}</span>
              ) : (
                <input
                  type="text"
                  className="dashboard-grid-no-drag min-w-0 flex-1 rounded border border-surface-border bg-black/40 px-2 py-1 text-sm text-white"
                  value={col.title}
                  onChange={(e) => updateColTitle(ci, e.target.value)}
                />
              )}
              {!readOnly && columns.length > 1 ? (
                <button
                  type="button"
                  className="shrink-0 rounded px-1.5 text-xs text-red-400 hover:bg-white/5"
                  title={t("dashboard:kanbanDeleteColumn")}
                  onClick={() => removeColumn(ci)}
                >
                  ×
                </button>
              ) : null}
            </div>
            <div className="flex min-h-[80px] flex-col gap-2">
              {col.cards.map((card) => (
                <div
                  key={card.id}
                  className="rounded-md border border-white/5 bg-surface-raised/80 p-2 shadow-sm"
                >
                  {readOnly ? (
                    <p className="text-sm text-neutral-200">{card.title || t("dashboard:kanbanCardTitleEmpty")}</p>
                  ) : (
                    <>
                      <input
                        type="text"
                        placeholder={t("dashboard:kanbanCardPlaceholder")}
                        className="dashboard-grid-no-drag mb-2 w-full rounded border border-surface-border bg-black/40 px-2 py-1 text-sm text-white"
                        value={card.title}
                        onChange={(e) => updateCardTitle(ci, card.id, e.target.value)}
                      />
                      <div className="flex flex-wrap items-center gap-2">
                        <select
                          className="dashboard-grid-no-drag max-w-full flex-1 rounded border border-surface-border bg-black/40 px-1 py-0.5 text-[10px] text-neutral-200"
                          value={ci}
                          onChange={(e) => moveCard(ci, card.id, Number(e.target.value))}
                          title={t("dashboard:kanbanMoveColumn")}
                        >
                          {columns.map((c, ti) => (
                            <option key={c.id} value={ti}>
                              → {c.title || t("dashboard:kanbanColumnFallback", { index: ti + 1 })}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="text-[10px] text-red-400 hover:underline"
                          onClick={() => removeCard(ci, card.id)}
                        >
                          {t("dashboard:delete")}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
            {!readOnly ? (
              <button
                type="button"
                className="dashboard-grid-no-drag mt-2 rounded-md border border-dashed border-white/15 py-1.5 text-xs text-surface-muted hover:border-sky-500/40 hover:text-sky-300"
                onClick={() => addCard(ci)}
              >
                {t("dashboard:kanbanAddCard")}
              </button>
            ) : null}
          </div>
        ))}
      </div>
      {columns.length === 0 && !readOnly ? (
        <p className="text-center text-sm text-surface-muted">{t("dashboard:kanbanEmptyHint")}</p>
      ) : null}
    </section>
  );
}

const mdClass = {
  p: "mb-2 last:mb-0 leading-relaxed text-neutral-200",
  h1: "mt-3 mb-2 text-xl font-semibold text-white first:mt-0",
  h2: "mt-3 mb-2 text-lg font-semibold text-white",
  h3: "mt-2 mb-1 text-base font-medium text-white",
  ul: "my-2 list-disc pl-5 text-neutral-200",
  ol: "my-2 list-decimal pl-5 text-neutral-200",
  li: "my-0.5",
  a: "text-sky-400 underline hover:text-sky-300",
  code: "rounded bg-white/10 px-1 py-0.5 font-mono text-[13px] text-sky-200",
  pre: "my-2 overflow-x-auto rounded-lg border border-white/10 bg-black/50 p-3 text-sm",
  blockquote: "border-l-2 border-sky-500/50 pl-3 italic text-surface-muted",
  table: "my-2 w-full border-collapse text-sm",
  th: "border border-white/10 bg-white/5 px-2 py-1 text-left text-white",
  td: "border border-white/10 px-2 py-1 text-neutral-200",
};

export function RichMarkdownBlockBody(props: {
  dp: string;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  sectionTitle: string;
  placeholder: string;
  readOnly: boolean;
}) {
  const { dp, data, setData, sectionTitle, placeholder, readOnly } = props;
  const { t } = useTranslation(["dashboard"]);
  const raw = dp ? getPath(data, dp) : "";
  const text = typeof raw === "string" ? raw : "";

  const preview = (
    <div className="min-h-[160px] overflow-y-auto rounded-lg border border-white/10 bg-black/30 p-3 text-sm">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className={mdClass.p}>{children}</p>,
          h1: ({ children }) => <h1 className={mdClass.h1}>{children}</h1>,
          h2: ({ children }) => <h2 className={mdClass.h2}>{children}</h2>,
          h3: ({ children }) => <h3 className={mdClass.h3}>{children}</h3>,
          ul: ({ children }) => <ul className={mdClass.ul}>{children}</ul>,
          ol: ({ children }) => <ol className={mdClass.ol}>{children}</ol>,
          li: ({ children }) => <li className={mdClass.li}>{children}</li>,
          a: ({ href, children }) => (
            <a href={href} className={mdClass.a} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          code: ({ className, children, ...rest }) => {
            const isBlock = String(className || "").includes("language-");
            if (isBlock) {
              return (
                <code className={`${mdClass.code} block whitespace-pre`} {...rest}>
                  {children}
                </code>
              );
            }
            return (
              <code className={mdClass.code} {...rest}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className={mdClass.pre}>{children}</pre>,
          blockquote: ({ children }) => (
            <blockquote className={mdClass.blockquote}>{children}</blockquote>
          ),
          table: ({ children }) => <table className={mdClass.table}>{children}</table>,
          th: ({ children }) => <th className={mdClass.th}>{children}</th>,
          td: ({ children }) => <td className={mdClass.td}>{children}</td>,
        }}
      >
        {text || t("dashboard:markdownEmpty")}
      </ReactMarkdown>
    </div>
  );

  if (readOnly) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
        <h3 className="mb-3 text-sm font-medium text-white">{sectionTitle}</h3>
        {preview}
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-surface-border bg-surface-raised/60 p-4">
      <h3 className="mb-3 text-sm font-medium text-white">{sectionTitle}</h3>
      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <label className="mb-1 block text-[10px] uppercase text-surface-muted">{t("dashboard:markdownLabel")}</label>
          <textarea
            className="dashboard-grid-no-drag min-h-[220px] w-full resize-y rounded-lg border border-surface-border bg-black/35 px-3 py-2 font-mono text-sm text-neutral-100 outline-none focus:border-sky-500/50"
            placeholder={placeholder}
            value={text}
            onChange={(e) => setData((d) => setPath(d, dp, e.target.value))}
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] uppercase text-surface-muted">{t("dashboard:markdownPreview")}</label>
          {preview}
        </div>
      </div>
    </section>
  );
}
