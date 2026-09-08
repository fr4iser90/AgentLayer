import type { Dispatch, SetStateAction } from "react";

import { DashboardCanvasSurface } from "./DashboardCanvasSurface";
import { DashboardGridInner } from "./DashboardGridInner";
import { layoutModeOf } from "./layoutMode";
import type { UiBlock, UiLayout } from "./types";

export { DashboardGridInner } from "./DashboardGridInner";

export function DashboardGridCanvas(props: {
  layout: UiLayout;
  setLayout: Dispatch<SetStateAction<UiLayout>>;
  data: Record<string, unknown>;
  setData: Dispatch<SetStateAction<Record<string, unknown>>>;
  editMode: boolean;
  contentReadOnly?: boolean;
  interactOnly?: boolean;
  dashboardId?: string | null;
  hideToolbar?: boolean;
  onPinBlock?: (blockId: string) => void;
  onPinBlockToChat?: (blockId: string) => void;
  chatFocusedBlockId?: string | null;
  onBlockPropsSave?: (blockId: string, nextProps: UiBlock["props"]) => void | Promise<void>;
  blockSettingsAutoSave?: boolean;
  blockSettingsSaving?: boolean;
  unreadBlockIds?: Set<string>;
  highlightBlockId?: string | null;
  onBlockSeen?: (blockId: string) => void;
  /** Grow to fill the parent flex column (canvas boards). */
  fillViewport?: boolean;
}) {
  const { fillViewport, ...gridProps } = props;
  if (layoutModeOf(props.layout) === "canvas") {
    return <DashboardCanvasSurface {...props} fillViewport={fillViewport} />;
  }
  return (
    <DashboardGridInner
      {...gridProps}
      depth={0}
      rootLayout={props.layout}
      setRootLayout={props.setLayout}
    />
  );
}
