import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { DashboardGridCanvas } from "./DashboardGridCanvas";
import { applyLayoutProposal } from "./layoutProposalShared";
import { useLayoutProposalSet } from "./useLayoutProposalSet";

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
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t("dashboard:layoutProposalsTitle")}
    >
      <div className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-t-2xl border border-surface-border bg-[#111] shadow-2xl sm:rounded-2xl">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-surface-border px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-white">{t("dashboard:layoutProposalsTitle")}</h2>
            <p className="text-xs text-neutral-400">{t("dashboard:layoutProposalsSubtitle")}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-surface-border px-2.5 py-1 text-xs text-neutral-300 hover:bg-white/5"
          >
            {t("dashboard:layoutProposalsClose")}
          </button>
        </header>

        {loading ? (
          <div className="px-4 py-8 text-sm text-neutral-400">{t("dashboard:layoutProposalsLoading")}</div>
        ) : errText && !proposalSet ? (
          <div className="mx-4 my-4 rounded-lg border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
            {errText}
          </div>
        ) : proposalSet ? (
          <>
            <div className="flex shrink-0 gap-2 overflow-x-auto border-b border-surface-border px-4 py-2">
              {proposalSet.proposals.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(p.id);
                    setConfirmId(null);
                  }}
                  className={`shrink-0 rounded-lg border px-3 py-2 text-left text-xs transition ${
                    selectedId === p.id
                      ? "border-emerald-500/60 bg-emerald-950/30 text-white"
                      : "border-surface-border bg-black/20 text-neutral-300 hover:bg-white/5"
                  }`}
                >
                  <div className="font-medium">{p.title}</div>
                  {p.summary ? (
                    <div className="mt-0.5 max-w-[14rem] truncate text-neutral-500">{p.summary}</div>
                  ) : null}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {selected ? (
                <div className="overflow-hidden rounded-xl border border-surface-border bg-[#0a0a0a]">
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
              <div className="mx-4 mb-2 rounded border border-red-500/40 bg-red-950/30 px-3 py-2 text-xs text-red-200">
                {applyErr}
              </div>
            ) : null}

            <footer className="flex shrink-0 items-center justify-end gap-2 border-t border-surface-border px-4 py-3">
              {confirmId === selectedId && selected ? (
                <>
                  <span className="mr-auto text-xs text-amber-200/90">
                    {t("dashboard:layoutProposalsConfirm", { title: selected.title })}
                  </span>
                  <button
                    type="button"
                    disabled={applyBusy}
                    onClick={() => setConfirmId(null)}
                    className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-neutral-300 hover:bg-white/5"
                  >
                    {t("dashboard:layoutProposalsCancel")}
                  </button>
                  <button
                    type="button"
                    disabled={applyBusy}
                    onClick={() => void applyProposal(selected.id)}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                  >
                    {applyBusy ? t("dashboard:saving") : t("dashboard:layoutProposalsApply")}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  disabled={!selected || applyBusy}
                  onClick={() => selected && setConfirmId(selected.id)}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
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
