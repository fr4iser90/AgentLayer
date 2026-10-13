import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import {
  hasProposal,
  parseProposalContent,
  stripProposalBlocks,
  type Proposal,
  type ProposalOption,
} from "../../lib/proposalParser";

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80 ? "text-badge-success" : pct >= 60 ? "text-badge-warning" : "text-badge-danger";
  return <span className={`text-meta font-medium ${color}`}>{pct}%</span>;
}

export function ProposalCard({
  proposal,
  selected,
  onSelect,
}: {
  proposal: Proposal;
  selected: string | null;
  onSelect: (option: ProposalOption) => void;
}) {
  return (
    <div className="my-wide rounded-sheet border border-accent/40 bg-[#111827] shadow-lg">
      <div className="border-b border-accent/30 px-wide py-soft">
        <div className="flex items-center gap-base">
          <svg
            className="h-4 w-4 text-accent"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            />
          </svg>
          <h3 className="text-sm font-semibold text-badge-accent">{proposal.title}</h3>
        </div>
      </div>
      <div className="p-soft">
        <ul className="flex flex-col gap-base">
          {proposal.options.map((opt) => {
            const isSelected = selected === opt.id;
            return (
              <li key={opt.id}>
                <button
                  type="button"
                  className={`w-full rounded-card border px-wide py-soft text-left transition-all ${
                    isSelected
                      ? "border-accent bg-accent-subtle ring-1 ring-accent/50"
                      : "border-line bg-black/20 hover:border-accent/50 hover:bg-white/5"
                  }`}
                  onClick={() => onSelect(opt)}
                >
                  <div className="flex items-center justify-between gap-soft">
                    <div className="flex items-center gap-soft">
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-pill border text-meta font-bold ${
                          isSelected
                            ? "border-accent bg-accent text-ink-on-fill"
                            : "border-line text-ink-muted"
                        }`}
                      >
                        {isSelected ? (
                          <Check aria-hidden className="h-3 w-3" />
                        ) : (
                          proposal.options.indexOf(opt) + 1
                        )}
                      </span>
                      <span className="text-sm font-medium text-ink-primary">{opt.label}</span>
                    </div>
                    {opt.confidence != null ? <ConfidenceBadge value={opt.confidence} /> : null}
                  </div>
                  {opt.description ? (
                    <p className="mt-snug pl-7 text-xs leading-relaxed text-ink-muted">
                      {opt.description}
                    </p>
                  ) : null}
                  {opt.actions && opt.actions.length > 0 ? (
                    <ul className="mt-base pl-7">
                      {opt.actions.map((action, ai) => (
                        <li
                          key={ai}
                          className="flex items-center gap-snug text-meta text-ink-muted"
                        >
                          <span className="text-ink-muted">→</span>
                          {action}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

type AssistantProposalBodyProps = {
  content: string;
  selectedByProposalId: Map<string, string | null>;
  onSelectOption: (proposal: Proposal, option: ProposalOption) => void;
};

function ProposalParseErrorBanner({ count }: { count: number }) {
  const { t } = useTranslation(["chat"]);
  return (
    <p
      className="my-base rounded-card border border-warning/40 bg-warning-subtle px-soft py-base text-xs text-badge-warning"
      role="status"
    >
      {t("chat:proposalParseError", { count })}
    </p>
  );
}

export function AssistantProposalBody({
  content,
  selectedByProposalId,
  onSelectOption,
}: AssistantProposalBodyProps) {
  const { proposals, failedBlockCount } = parseProposalContent(content);
  const bodyText = stripProposalBlocks(content);
  const showParseError = failedBlockCount > 0;

  if (proposals.length === 0) {
    return (
      <div className="space-y-base">
        {bodyText ? <div className="whitespace-pre-wrap">{bodyText}</div> : null}
        {showParseError ? <ProposalParseErrorBanner count={failedBlockCount} /> : null}
        {!bodyText && !showParseError && hasProposal(content) ? (
          <ProposalParseErrorBanner count={1} />
        ) : null}
        {!bodyText && !showParseError && !hasProposal(content) ? (
          <div className="whitespace-pre-wrap">{content}</div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-base">
      {bodyText ? <div className="whitespace-pre-wrap">{bodyText}</div> : null}
      {showParseError ? <ProposalParseErrorBanner count={failedBlockCount} /> : null}
      {proposals.map((p) => (
        <ProposalCard
          key={p.id}
          proposal={p}
          selected={selectedByProposalId.get(p.id) ?? null}
          onSelect={(opt) => onSelectOption(p, opt)}
        />
      ))}
    </div>
  );
}
