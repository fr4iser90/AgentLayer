import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { DashboardGridCanvas } from "./DashboardGridCanvas";
import { applyLayoutProposal } from "./layoutProposalShared";
import { useLayoutProposalSet } from "./useLayoutProposalSet";

type Props = {
  dashboardId: string;
  setId: string;
  data: Record<string, unknown>;
  onEnlarge: (proposalId: string) => void;
  onApplied: () => void;
};

export function DashboardLayoutProposalInline({
  dashboardId,
  setId,
  data,
  onEnlarge,
  onApplied,
}: Props) {
  const { t } = useTranslation(["dashboard"]);
  const auth = useAuth();
  const { loading, error, notFound, proposalSet } = useLayoutProposalSet(dashboardId, setId);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyErr, setApplyErr] = useState<string | null>(null);

  const noopLayout = useCallback(() => {}, []);
  const noopData = useCallback(() => {}, []);

  const handleApply = useCallback(
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
    },
    [auth, dashboardId, onApplied, setId]
  );

  if (loading) {
    return (
      <div className="mt-2 rounded-lg border border-white/10 bg-black/30 px-2 py-3 text-[11px] text-surface-muted">
        {t("dashboard:layoutProposalsLoading")}
      </div>
    );
  }

  if (notFound || error || !proposalSet) {
    return (
      <div className="mt-2 rounded-lg border border-red-500/30 bg-red-950/20 px-2 py-2 text-[11px] text-red-200">
        {t("dashboard:layoutProposalsEmpty")}
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2">
      <p className="text-[10px] font-medium uppercase tracking-wide text-emerald-400/90">
        {t("dashboard:layoutProposalsInlineHint")}
      </p>
      {applyErr ? (
        <p className="rounded border border-red-500/30 bg-red-950/20 px-2 py-1 text-[10px] text-red-200">
          {applyErr}
        </p>
      ) : null}
      <div className="flex flex-col gap-2">
        {proposalSet.proposals.map((p) => {
          const confirming = confirmId === p.id;
          return (
            <article
              key={p.id}
              className="overflow-hidden rounded-lg border border-emerald-500/25 bg-[#0d1210]"
            >
              <div className="border-b border-white/5 px-2 py-1.5">
                <div className="text-[11px] font-semibold text-white">{p.title}</div>
                {p.summary ? (
                  <div className="mt-0.5 text-[10px] leading-snug text-neutral-400">{p.summary}</div>
                ) : null}
              </div>
              <button
                type="button"
                className="block w-full cursor-zoom-in text-left"
                onClick={() => onEnlarge(p.id)}
                aria-label={t("dashboard:layoutProposalsEnlarge", { title: p.title })}
              >
                <div className="relative h-[200px] overflow-hidden bg-[#080808]">
                  <div className="pointer-events-none absolute inset-0 origin-top-left scale-[0.38]">
                    <div className="w-[265%]">
                      <DashboardGridCanvas
                        layout={p.ui_layout}
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
              </button>
              <div className="flex items-center justify-end gap-1.5 border-t border-white/5 px-2 py-1.5">
                <button
                  type="button"
                  className="rounded border border-surface-border px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5"
                  onClick={() => onEnlarge(p.id)}
                >
                  {t("dashboard:layoutProposalsEnlargeShort")}
                </button>
                {confirming ? (
                  <>
                    <button
                      type="button"
                      disabled={applyBusy}
                      className="rounded border border-surface-border px-2 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5"
                      onClick={() => setConfirmId(null)}
                    >
                      {t("dashboard:layoutProposalsCancel")}
                    </button>
                    <button
                      type="button"
                      disabled={applyBusy}
                      className="rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                      onClick={() => void handleApply(p.id)}
                    >
                      {applyBusy ? t("dashboard:saving") : t("dashboard:layoutProposalsApplyConfirm")}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={applyBusy}
                    className="rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                    onClick={() => setConfirmId(p.id)}
                  >
                    {t("dashboard:layoutProposalsApply")}
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
