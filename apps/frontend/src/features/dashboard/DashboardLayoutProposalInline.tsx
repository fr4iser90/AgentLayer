import { useCallback, useState } from "react";
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
      <div className="mt-base rounded-card border border-line bg-black/30 px-base py-soft text-meta text-ink-muted">
        {t("dashboard:layoutProposalsLoading")}
      </div>
    );
  }

  if (notFound || error || !proposalSet) {
    return (
      <div className="mt-base rounded-card border border-danger/30 bg-danger-subtle px-base py-base text-meta text-badge-danger">
        {t("dashboard:layoutProposalsEmpty")}
      </div>
    );
  }

  return (
    <div className="mt-base space-y-base">
      <p className="text-meta font-medium uppercase tracking-wide text-success">
        {t("dashboard:layoutProposalsInlineHint")}
      </p>
      {applyErr ? (
        <p className="rounded-tile border border-danger/30 bg-danger-subtle px-base py-tight text-meta text-badge-danger">
          {applyErr}
        </p>
      ) : null}
      <div className="flex flex-col gap-base">
        {proposalSet.proposals.map((p) => {
          const confirming = confirmId === p.id;
          return (
            <article
              key={p.id}
              className="overflow-hidden rounded-card border border-success/25 bg-[#0d1210]"
            >
              <div className="border-b border-line-subtle px-base py-snug">
                <div className="text-meta font-semibold text-ink-primary">{p.title}</div>
                {p.summary ? (
                  <div className="mt-hair text-meta leading-snug text-ink-muted">{p.summary}</div>
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
              <div className="flex items-center justify-end gap-snug border-t border-line-subtle px-base py-snug">
                <button
                  type="button"
                  className="rounded-tile border border-line px-base py-hair text-meta text-ink-secondary hover:bg-white/5"
                  onClick={() => onEnlarge(p.id)}
                >
                  {t("dashboard:layoutProposalsEnlargeShort")}
                </button>
                {confirming ? (
                  <>
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
                      className="rounded-tile bg-success px-base py-hair text-meta font-medium text-ink-on-fill hover:bg-success-hover disabled:opacity-50"
                      onClick={() => void handleApply(p.id)}
                    >
                      {applyBusy ? t("dashboard:saving") : t("dashboard:layoutProposalsApplyConfirm")}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={applyBusy}
                    className="rounded-tile bg-success px-base py-hair text-meta font-medium text-ink-on-fill hover:bg-success-hover disabled:opacity-50"
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
