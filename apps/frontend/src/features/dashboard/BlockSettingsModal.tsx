import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { blockTypeLabel } from "./layoutTree";
import {
  applyDisplayPreset,
  previewDataAtPath,
  type DisplayPresetId,
} from "./blockSettingsPreview";
import type { UiBlock } from "./types";

type TabId = "general" | "data" | "display";

type Props = {
  block: UiBlock;
  data: Record<string, unknown>;
  /** When false, changes apply to layout draft only (save layout separately). */
  autoSave: boolean;
  saving?: boolean;
  onClose: () => void;
  onSave: (nextProps: UiBlock["props"]) => void | Promise<void>;
};

function strList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((x) => String(x).trim()).filter(Boolean);
}

function supportsDataTab(type: string): boolean {
  return type !== "dashboard_ref" && type !== "share_widget" && type !== "section";
}

function supportsDisplayPreset(type: string): boolean {
  return type === "card_grid" || type === "table" || type === "chart" || type === "kanban";
}

export function BlockSettingsModal({
  block,
  data,
  autoSave,
  saving = false,
  onClose,
  onSave,
}: Props) {
  const { t } = useTranslation(["dashboard"]);
  const [tab, setTab] = useState<TabId>("general");
  const [title, setTitle] = useState("");
  const [dataPath, setDataPath] = useState("");
  const [fillGrid, setFillGrid] = useState(false);
  const [gridColumns, setGridColumns] = useState(3);
  const [enableSearch, setEnableSearch] = useState(false);
  const [enableRowDetail, setEnableRowDetail] = useState(false);
  const [cardFields, setCardFields] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const columnFields = useMemo(
    () =>
      Array.isArray(block.props.columns)
        ? block.props.columns
            .map((c) => (c && typeof c === "object" && "field" in c ? String(c.field) : ""))
            .filter(Boolean)
        : [],
    [block.props.columns]
  );

  const dataPreview = useMemo(() => previewDataAtPath(data, dataPath), [data, dataPath]);

  useEffect(() => {
    setTitle(String(block.props.title ?? ""));
    setDataPath(String(block.props.dataPath ?? ""));
    setFillGrid(block.props.fillGrid === true);
    setGridColumns(Math.min(5, Math.max(1, Number(block.props.gridColumns) || 3)));
    setEnableSearch(block.props.enableSearch === true);
    setEnableRowDetail(block.props.enableRowDetail === true);
    setCardFields(strList(block.props.cardFields));
    setTab("general");
  }, [block]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggleCardField = (field: string) => {
    setCardFields((prev) =>
      prev.includes(field) ? prev.filter((f) => f !== field) : [...prev, field]
    );
  };

  const buildNextProps = (): UiBlock["props"] => {
    const next: UiBlock["props"] = {
      ...block.props,
      title: title.trim(),
      dataPath: dataPath.trim(),
      fillGrid,
    };
    if (block.type === "card_grid") {
      next.gridColumns = gridColumns;
      next.enableSearch = enableSearch;
      next.enableRowDetail = enableRowDetail;
      next.cardFields = cardFields.length ? cardFields : columnFields.slice(0, 4);
    }
    if (block.type === "table") {
      next.enableSearch = enableSearch;
      next.enableRowDetail = enableRowDetail;
    }
    return next;
  };

  const applyPreset = (preset: DisplayPresetId) => {
    const patch = applyDisplayPreset(block.type, preset);
    if (typeof patch.fillGrid === "boolean") setFillGrid(patch.fillGrid);
    if (typeof patch.gridColumns === "number") setGridColumns(patch.gridColumns);
    if (typeof patch.enableSearch === "boolean") setEnableSearch(patch.enableSearch);
    if (typeof patch.enableRowDetail === "boolean") setEnableRowDetail(patch.enableRowDetail);
  };

  const save = async () => {
    setBusy(true);
    try {
      await onSave(buildNextProps());
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const tabs: { id: TabId; label: string }[] = [
    { id: "general", label: t("dashboard:blockSettingsTabGeneral") },
    ...(supportsDataTab(block.type)
      ? [{ id: "data" as TabId, label: t("dashboard:blockSettingsTabData") }]
      : []),
    { id: "display", label: t("dashboard:blockSettingsTabDisplay") },
  ];

  const previewText = (() => {
    if (dataPreview.status === "array") {
      return t("dashboard:blockSettingsPreviewArray", { count: dataPreview.count });
    }
    if (dataPreview.status === "object") {
      return t("dashboard:blockSettingsPreviewObject", {
        keys: dataPreview.keys.join(", ") || "—",
      });
    }
    if (dataPreview.status === "primitive") {
      return t("dashboard:blockSettingsPreviewPrimitive", { sample: dataPreview.sample });
    }
    return t(`dashboard:${dataPreview.messageKey}`);
  })();

  const saveLabel = autoSave
    ? t("dashboard:blockSettingsSaveAuto")
    : t("dashboard:blockSettingsSaveDraft");
  const isSaving = saving || busy;

  return (
    <div
      className="fixed inset-0 z-[80] flex justify-end bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="block-settings-title"
      onClick={onClose}
    >
      <aside
        className="flex h-full w-full max-w-md flex-col border-l border-surface-border bg-[#111] shadow-2xl sm:max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="shrink-0 border-b border-surface-border px-4 py-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h2 id="block-settings-title" className="text-sm font-semibold text-white">
                {t("dashboard:blockSettingsTitle")}
              </h2>
              <p className="mt-0.5 text-[11px] text-surface-muted">
                {blockTypeLabel(block.type)} ·{" "}
                <span className="font-mono text-white/70">{block.id}</span>
              </p>
            </div>
            <button
              type="button"
              className="rounded px-2 py-1 text-surface-muted hover:bg-white/10 hover:text-white"
              onClick={onClose}
              aria-label={t("dashboard:blockSettingsClose")}
            >
              ×
            </button>
          </div>
          <nav className="mt-3 flex gap-1 border-b border-white/5 pb-0" aria-label={t("dashboard:blockSettingsTabsAria")}>
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                className={[
                  "rounded-t-md px-3 py-1.5 text-xs font-medium transition-colors",
                  tab === item.id
                    ? "border border-b-0 border-white/15 bg-black/40 text-white"
                    : "text-surface-muted hover:text-white",
                ].join(" ")}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 text-sm">
          {tab === "general" ? (
            <div className="space-y-4">
              <p className="text-xs leading-snug text-surface-muted">
                {autoSave
                  ? t("dashboard:blockSettingsIntroAutoSave")
                  : t("dashboard:blockSettingsIntroDraft")}
              </p>
              <label className="block space-y-1">
                <span className="text-[11px] text-surface-muted">
                  {t("dashboard:blockSettingsTitleLabel")}
                </span>
                <input
                  className="w-full rounded-lg border border-surface-border bg-black/40 px-3 py-2 text-white outline-none focus:border-sky-500/50"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <div className="space-y-1">
                <span className="text-[11px] text-surface-muted">{t("dashboard:blockSettingsBlockId")}</span>
                <p className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-[11px] text-neutral-300">
                  {block.id}
                </p>
              </div>
            </div>
          ) : null}

          {tab === "data" && supportsDataTab(block.type) ? (
            <div className="space-y-4">
              <label className="block space-y-1">
                <span className="text-[11px] text-surface-muted">{t("dashboard:blockSettingsDataPath")}</span>
                <input
                  className="w-full rounded-lg border border-surface-border bg-black/40 px-3 py-2 font-mono text-xs text-white outline-none focus:border-sky-500/50"
                  value={dataPath}
                  onChange={(e) => setDataPath(e.target.value)}
                  placeholder={t("dashboard:blockSettingsDataPathPlaceholder")}
                />
                <span className="text-[10px] text-surface-muted">{t("dashboard:blockSettingsDataPathHint")}</span>
              </label>
              <div className="rounded-lg border border-sky-500/20 bg-sky-950/20 px-3 py-2 text-xs text-sky-100/90">
                <span className="block text-[10px] font-medium uppercase tracking-wide text-sky-300/80">
                  {t("dashboard:blockSettingsPreviewLabel")}
                </span>
                {previewText}
              </div>
              {block.type === "card_grid" && columnFields.length ? (
                <div className="space-y-2">
                  <span className="text-[11px] text-surface-muted">{t("dashboard:blockSettingsCardFields")}</span>
                  <ul className="flex flex-wrap gap-2">
                    {columnFields.map((field) => (
                      <li key={field}>
                        <label className="flex cursor-pointer items-center gap-1.5 rounded border border-white/10 bg-black/30 px-2 py-1 text-xs">
                          <input
                            type="checkbox"
                            checked={cardFields.includes(field)}
                            onChange={() => toggleCardField(field)}
                          />
                          {field}
                        </label>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          {tab === "display" ? (
            <div className="space-y-4">
              {supportsDisplayPreset(block.type) ? (
                <div className="space-y-2">
                  <span className="text-[11px] text-surface-muted">{t("dashboard:blockSettingsPreset")}</span>
                  <div className="flex flex-wrap gap-2">
                    {(["compact", "standard", "comfortable"] as DisplayPresetId[]).map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        className="rounded-lg border border-white/15 bg-black/30 px-3 py-1.5 text-xs text-neutral-200 hover:border-sky-500/40 hover:bg-sky-950/30"
                        onClick={() => applyPreset(preset)}
                      >
                        {t(`dashboard:blockSettingsPreset_${preset}`)}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={fillGrid}
                  onChange={(e) => setFillGrid(e.target.checked)}
                />
                <span>
                  <span className="block text-white">{t("dashboard:blockSettingsFillGrid")}</span>
                  <span className="text-[10px] text-surface-muted">
                    {t("dashboard:blockSettingsFillGridHint")}
                  </span>
                </span>
              </label>
              {block.type === "card_grid" ? (
                <>
                  <label className="block space-y-1">
                    <span className="text-[11px] text-surface-muted">
                      {t("dashboard:blockSettingsGridColumns")}
                    </span>
                    <input
                      type="number"
                      min={1}
                      max={5}
                      className="w-24 rounded-lg border border-surface-border bg-black/40 px-3 py-2 text-white"
                      value={gridColumns}
                      onChange={(e) => setGridColumns(Number(e.target.value) || 3)}
                    />
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={enableSearch}
                      onChange={(e) => setEnableSearch(e.target.checked)}
                    />
                    <span>{t("dashboard:blockSettingsEnableSearch")}</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={enableRowDetail}
                      onChange={(e) => setEnableRowDetail(e.target.checked)}
                    />
                    <span>{t("dashboard:blockSettingsEnableRowDetail")}</span>
                  </label>
                </>
              ) : null}
              {block.type === "table" ? (
                <>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={enableSearch}
                      onChange={(e) => setEnableSearch(e.target.checked)}
                    />
                    <span>{t("dashboard:blockSettingsEnableSearch")}</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={enableRowDetail}
                      onChange={(e) => setEnableRowDetail(e.target.checked)}
                    />
                    <span>{t("dashboard:blockSettingsEnableRowDetail")}</span>
                  </label>
                </>
              ) : null}
            </div>
          ) : null}
        </div>

        <footer className="flex shrink-0 justify-end gap-2 border-t border-surface-border px-4 py-3">
          <button
            type="button"
            className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-neutral-300 hover:bg-white/5"
            onClick={onClose}
            disabled={isSaving}
          >
            {t("dashboard:blockSettingsCancel")}
          </button>
          <button
            type="button"
            className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            onClick={() => void save()}
            disabled={isSaving}
          >
            {isSaving ? t("dashboard:saving") : saveLabel}
          </button>
        </footer>
      </aside>
    </div>
  );
}
