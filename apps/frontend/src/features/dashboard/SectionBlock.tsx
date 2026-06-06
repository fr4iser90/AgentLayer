import { useCallback, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import { AgentUpdateBadge } from "./AgentUpdateBadge";
import { DashboardGridInner } from "./DashboardGridInner";
import type { UiBlock, UiLayout } from "./types";
import { emptyNestedLayout, normalizeNestedLayout, sectionHasUnreadNested } from "./layoutTree";

export function SectionBlockBody(props: {
  block: UiBlock;
  rootLayout: UiLayout;
  setRootLayout: Dispatch<SetStateAction<UiLayout>>;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  editMode: boolean;
  contentReadOnly: boolean;
  dashboardId: string | null;
  unreadBlockIds?: Set<string>;
  highlightBlockId?: string | null;
  onBlockSeen?: (blockId: string) => void;
}) {
  const { t } = useTranslation(["dashboard", "notifications"]);
  const {
    block,
    rootLayout,
    setRootLayout,
    data,
    setData,
    editMode,
    contentReadOnly,
    dashboardId,
    unreadBlockIds,
    highlightBlockId,
    onBlockSeen,
  } = props;

  const nested = normalizeNestedLayout(block.props.nested);
  const [collapsed, setCollapsed] = useState(block.props.collapsed === true);
  const sectionUnread = sectionHasUnreadNested(block, unreadBlockIds);

  const setNestedLayout = useCallback(
    (updater: SetStateAction<UiLayout>) => {
      setRootLayout((prev) => ({
        version: 2,
        blocks: prev.blocks.map((b) => {
          if (b.id !== block.id) return b;
          const curNested = normalizeNestedLayout(b.props.nested);
          const nextNested = typeof updater === "function" ? updater(curNested) : updater;
          return {
            ...b,
            props: {
              ...b.props,
              nested: nextNested,
            },
          };
        }),
      }));
    },
    [block.id, setRootLayout]
  );

  const patchSectionProps = useCallback(
    (patch: Record<string, unknown>) => {
      setRootLayout((prev) => ({
        version: 2,
        blocks: prev.blocks.map((b) =>
          b.id === block.id ? { ...b, props: { ...b.props, ...patch } } : b
        ),
      }));
    },
    [block.id, setRootLayout]
  );

  const title = block.props.title?.trim() || t("dashboard:sectionFallback");

  return (
    <section className="relative flex h-full min-h-0 flex-col rounded-lg border border-white/5 bg-black/20">
      {sectionUnread && collapsed ? (
        <AgentUpdateBadge
          variant="corner"
          title={t("notifications:agentUpdateBadgeSection")}
        />
      ) : null}
      <header className="dashboard-grid-no-drag flex flex-wrap items-center gap-2 border-b border-white/5 px-3 py-2">
        {editMode && !contentReadOnly ? (
          <input
            type="text"
            className="min-w-0 flex-1 rounded-md border border-surface-border bg-black/40 px-2 py-1 text-sm text-white outline-none focus:border-sky-500/50"
            value={block.props.title ?? ""}
            placeholder={t("dashboard:sectionTitlePlaceholder")}
            onChange={(e) => patchSectionProps({ title: e.target.value })}
          />
        ) : (
          <h3 className="min-w-0 flex-1 truncate text-sm font-medium text-white">{title}</h3>
        )}
        {sectionUnread && !collapsed ? (
          <AgentUpdateBadge variant="inline" title={t("notifications:agentUpdateBadgeSection")} />
        ) : null}
        <button
          type="button"
          className="dashboard-grid-no-drag rounded-md border border-surface-border px-2 py-1 text-[11px] text-surface-muted hover:bg-white/5"
          onClick={() => {
            const next = !collapsed;
            setCollapsed(next);
            patchSectionProps({ collapsed: next });
          }}
        >
          {collapsed ? t("dashboard:sectionExpand") : t("dashboard:sectionCollapse")}
        </button>
      </header>
      {!collapsed ? (
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {nested.blocks.length === 0 && !editMode ? (
            <p className="px-2 py-4 text-xs text-surface-muted">{t("dashboard:sectionEmpty")}</p>
          ) : (
            <DashboardGridInner
              layout={nested.blocks.length ? nested : emptyNestedLayout()}
              setLayout={setNestedLayout}
              data={data}
              setData={setData}
              editMode={editMode}
              contentReadOnly={contentReadOnly}
              dashboardId={dashboardId}
              depth={1}
              rootLayout={rootLayout}
              setRootLayout={setRootLayout}
              embedded
              unreadBlockIds={unreadBlockIds}
              highlightBlockId={highlightBlockId}
              onBlockSeen={onBlockSeen}
            />
          )}
        </div>
      ) : null}
    </section>
  );
}
