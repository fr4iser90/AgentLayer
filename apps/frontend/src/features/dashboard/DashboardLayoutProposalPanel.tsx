import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { DashboardGridCanvas } from "./DashboardGridCanvas";
import { applyLayoutProposal } from "./layoutProposalShared";
import { useLayoutProposalSet } from "./useLayoutProposalSet";
import { Button } from "../../ui/Button";

type Props = {
  dashboardId: string;
  setId: string;
  data: Record<string, unknown>;
  initialProposalId?: string | null;
  onApplied: () => void;
  onClose: () => void;
};

export function DashboardLayoutProposalPanel({
  dashboardId,
  setId,
  data,
  initialProposalId,
  onApplied,
  onClose,
}: Props) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const { loading, error, notFound, proposalSet } = useLayoutProposalSet(dashboardId, setId);
  const [selectedId, setSelectedId] = useState<string | null>(initialProposalId ?? null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyErr, setApplyErr] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  useEffect(() => {
    if (initialProposalId) setSelectedId(initialProposalId);
  }, [initialProposalId]);

  useEffect(() => {
    if (!proposalSet || selectedId) return;
    setSelectedId(proposalSet.proposals[0]?.id ?? null);
  }, [proposalSet, selectedId]);

  const selected = useMemo(
    () => proposalSet?.proposals.find((p) => p.id === selectedId) ?? null,
    [proposalSet, selectedId]
  );

  const noopLayout = useCallback(() => {}, []);
  const noopData = useCallback(() => {}, []);

  const applyProposal = useCallback(
    async (proposalId: string) => {
      setApplyBusy(true);
      setApplyErr(null);
      const result = await applyLayoutProposal(auth, dashboardId, setId, proposalId);
      setApplyBusy(false);
      if (!result.ok) {
        setApplyErr(result.error);
        return;
      }
      setConfirmId(null);
      onApplied();
      onClose();
    },
    [auth, dashboardId, onApplied, onClose, setId]
  );

  const errText = notFound
    ? t("dashboard:layoutProposalsEmpty")
    : error
      ? error
      : applyErr;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-wide"
      role="dialog"
      aria-modal="true"
      aria-label={t("dashboard:layoutProposalsTitle")}
    >
      <div className="flex max-h-[92vh] w-full max-w-dialogFull flex-col overflow-hidden rounded-t-sheet border border-line bg-[#111] shadow-2xl sm:rounded-sheet">
        <header className="flex shrink-0 items-center justify-between gap-soft border-b border-line px-wide py-soft">
          <div>
            <h2 className="text-sm font-semibold text-ink-primary">{t("dashboard:layoutProposalsTitle")}</h2>
            <p className="text-xs text-ink-muted">{t("dashboard:layoutProposalsSubtitle")}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-card border border-line px-firm py-tight text-xs text-ink-secondary hover:bg-white/5"
          >
            {t("dashboard:layoutProposalsClose")}
          </button>
        </header>

        {loading ? (
          <div className="px-wide py-deep text-sm text-ink-muted">{t("dashboard:layoutProposalsLoading")}</div>
        ) : errText && !proposalSet ? (
          <div className="mx-wide my-wide rounded-card border border-red-500/40 bg-red-950/30 px-soft py-base text-sm text-red-200">
            {errText}
          </div>
        ) : proposalSet ? (
          <>
            <div className="flex shrink-0 gap-base overflow-x-auto border-b border-line px-wide py-base">
              {proposalSet.proposals.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(p.id);
                    setConfirmId(null);
                  }}
                  className={`shrink-0 rounded-card border px-soft py-base text-left text-xs transition ${
                    selectedId === p.id
                      ? "border-emerald-500/60 bg-emerald-950/30 text-ink-primary"
                      : "border-line bg-black/20 text-ink-secondary hover:bg-white/5"
                  }`}
                >
                  <div className="font-medium">{p.title}</div>
                  {p.summary ? (
                    <div className="mt-hair max-w-chipWide truncate text-ink-muted">{p.summary}</div>
                  ) : null}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-wide">
              {selected ? (
                <div className="overflow-hidden rounded-sheet border border-line bg-[#0a0a0a]">
                  <div className="origin-top-left scale-[0.72] sm:scale-[0.82]">
                    <div className="w-[138%] sm:w-[122%]">
                      <DashboardGridCanvas
                        layout={selected.ui_layout}
                        setLayout={noopLayout}
                        data={data}
                        setData={noopData}
                        editMode={false}
                        contentReadOnly
                        dashboardId={dashboardId}
                        hideToolbar
                      />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            {applyErr ? (
              <div className="mx-wide mb-base rounded-tile border border-red-500/40 bg-red-950/30 px-soft py-base text-xs text-red-200">
                {applyErr}
              </div>
            ) : null}

            <footer className="flex shrink-0 items-center justify-end gap-base border-t border-line px-wide py-soft">
              {confirmId === selectedId && selected ? (
                <>
                  <span className="mr-auto text-xs text-amber-200/90">
                    {t("dashboard:layoutProposalsConfirm", { title: selected.title })}
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={applyBusy}
                    onClick={() => setConfirmId(null)}
                  >
                    {t("dashboard:layoutProposalsCancel")}
                  </Button>
                  <button
                    type="button"
                    disabled={applyBusy}
                    onClick={() => void applyProposal(selected.id)}
                    className="rounded-card bg-emerald-600 px-soft py-snug text-xs font-medium text-ink-on-fill hover:bg-emerald-500 disabled:opacity-50"
                  >
                    {applyBusy ? t("dashboard:saving") : t("dashboard:layoutProposalsApply")}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  disabled={!selected || applyBusy}
                  onClick={() => selected && setConfirmId(selected.id)}
                  className="rounded-card bg-emerald-600 px-wide py-base text-sm font-medium text-ink-on-fill hover:bg-emerald-500 disabled:opacity-50"
                >
                  {t("dashboard:layoutProposalsApply")}
                </button>
              )}
            </footer>
          </>
        ) : null}
      </div>
    </div>
  );
}
