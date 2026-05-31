import { useTranslation } from "react-i18next";
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
    pct >= 80 ? "text-emerald-300" : pct >= 60 ? "text-amber-300" : "text-red-300";
  return <span className={`text-[10px] font-medium ${color}`}>{pct}%</span>;
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
    <div className="my-4 rounded-xl border border-sky-800/40 bg-[#111827] shadow-lg">
      <div className="border-b border-sky-800/30 px-4 py-3">
        <div className="flex items-center gap-2">
          <svg
            className="h-4 w-4 text-sky-400"
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
          <h3 className="text-sm font-semibold text-sky-100">{proposal.title}</h3>
        </div>
      </div>
      <div className="p-3">
        <ul className="flex flex-col gap-2">
          {proposal.options.map((opt) => {
            const isSelected = selected === opt.id;
            return (
              <li key={opt.id}>
                <button
                  type="button"
                  className={`w-full rounded-lg border px-4 py-3 text-left transition-all ${
                    isSelected
                      ? "border-sky-500 bg-sky-950/50 ring-1 ring-sky-500/50"
                      : "border-surface-border bg-black/20 hover:border-sky-700/50 hover:bg-white/5"
                  }`}
                  onClick={() => onSelect(opt)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold ${
                          isSelected
                            ? "border-sky-400 bg-sky-500 text-white"
                            : "border-surface-border text-surface-muted"
                        }`}
                      >
                        {isSelected ? "✓" : proposal.options.indexOf(opt) + 1}
                      </span>
                      <span className="text-sm font-medium text-neutral-200">{opt.label}</span>
                    </div>
                    {opt.confidence != null ? <ConfidenceBadge value={opt.confidence} /> : null}
                  </div>
                  {opt.description ? (
                    <p className="mt-1.5 pl-7 text-xs leading-relaxed text-neutral-400">
                      {opt.description}
                    </p>
                  ) : null}
                  {opt.actions && opt.actions.length > 0 ? (
                    <ul className="mt-2 pl-7">
                      {opt.actions.map((action, ai) => (
                        <li
                          key={ai}
                          className="flex items-center gap-1.5 text-[11px] text-neutral-500"
                        >
                          <span className="text-surface-muted">→</span>
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
      className="my-2 rounded-lg border border-amber-700/40 bg-amber-950/35 px-3 py-2 text-xs text-amber-100/90"
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
      <div className="space-y-2">
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
    <div className="space-y-2">
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
