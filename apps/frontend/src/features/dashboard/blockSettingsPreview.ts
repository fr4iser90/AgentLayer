import { getPath } from "./dashboardDataPaths";

export type DataPathPreview =
  | { status: "missing"; messageKey: "blockSettingsPreviewMissing" }
  | { status: "empty"; messageKey: "blockSettingsPreviewEmpty" }
  | { status: "array"; count: number }
  | { status: "object"; keys: string[] }
  | { status: "primitive"; sample: string };

export function previewDataAtPath(
  data: Record<string, unknown>,
  path: string
): DataPathPreview {
  const p = path.trim();
  if (!p) {
    return { status: "missing", messageKey: "blockSettingsPreviewMissing" };
  }
  const raw = getPath(data, p);
  if (raw === undefined) {
    return { status: "missing", messageKey: "blockSettingsPreviewMissing" };
  }
  if (raw === null || raw === "") {
    return { status: "empty", messageKey: "blockSettingsPreviewEmpty" };
  }
  if (Array.isArray(raw)) {
    return { status: "array", count: raw.length };
  }
  if (typeof raw === "object") {
    const keys = Object.keys(raw as Record<string, unknown>).slice(0, 12);
    return { status: "object", keys };
  }
  const sample = String(raw);
  return { status: "primitive", sample: sample.length > 80 ? `${sample.slice(0, 80)}…` : sample };
}

export type DisplayPresetId = "compact" | "standard" | "comfortable";

export function applyDisplayPreset(
  blockType: string,
  preset: DisplayPresetId
): Partial<Record<string, unknown>> {
  if (blockType === "card_grid") {
    if (preset === "compact") {
      return {
        fillGrid: false,
        gridColumns: 4,
        enableSearch: false,
        enableRowDetail: false,
      };
    }
    if (preset === "comfortable") {
      return {
        fillGrid: true,
        gridColumns: 2,
        enableSearch: true,
        enableRowDetail: true,
      };
    }
    return {
      fillGrid: false,
      gridColumns: 3,
      enableSearch: true,
      enableRowDetail: true,
    };
  }
  if (blockType === "table") {
    if (preset === "compact") {
      return { fillGrid: false, enableSearch: false, enableRowDetail: false };
    }
    if (preset === "comfortable") {
      return { fillGrid: true, enableSearch: true, enableRowDetail: true };
    }
    return { fillGrid: false, enableSearch: true, enableRowDetail: true };
  }
  if (preset === "comfortable") return { fillGrid: true };
  if (preset === "compact") return { fillGrid: false };
  return { fillGrid: false };
}
