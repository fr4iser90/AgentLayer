/**
 * Proposal parser — extracts structured option proposals from LLM assistant messages.
 *
 * The LLM can embed a proposal in a code block with language `json-proposal`:
 *
 * ```json-proposal
 * {
 *   "title": "How should I fix this?",
 *   "options": [
 *     {"id": "1", "label": "Quick fix", "description": "Add a null check before..."},
 *     {"id": "2", "label": "Full refactor", "description": "Rewrite the module to..."}
 *   ]
 * }
 * ```
 */

export interface ProposalOption {
  id: string;
  label: string;
  description: string;
  actions?: string[];
  confidence?: number;
}

export interface Proposal {
  id: string;
  title: string;
  options: ProposalOption[];
}

export type ProposalParseResult = {
  proposals: Proposal[];
  /** Blocks with ```json-proposal fences that could not yield any clickable option. */
  failedBlockCount: number;
};

const PROPOSAL_RE = /```json-proposal\s*\n([\s\S]*?)```/g;

const SALVAGE_KEY_TYPOS = ["label", "description", "title", "id"] as const;

/** Fix common LLM JSON typos (e.g. `"label: Foo"` instead of `"label": "Foo"`). */
export function salvageProposalJsonText(trimmed: string): string {
  let s = trimmed.replace(/,\s*([}\]])/g, "$1");
  for (const key of SALVAGE_KEY_TYPOS) {
    s = s.replace(
      new RegExp(`"${key}:\\s*([^"]+?)"\\s*([,}])`, "g"),
      `"${key}": "$1"$2`
    );
  }
  return s;
}

function parseProposalJson(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim();
  const attempts = [trimmed, salvageProposalJsonText(trimmed)];
  for (const attempt of attempts) {
    try {
      const v = JSON.parse(attempt) as unknown;
      if (v && typeof v === "object" && !Array.isArray(v)) {
        return v as Record<string, unknown>;
      }
    } catch {
      /* try next */
    }
  }
  return null;
}

function mapProposalOptions(raw: unknown): ProposalOption[] {
  if (!Array.isArray(raw)) return [];
  return (raw as Array<Record<string, unknown>>)
    .filter((o) => o && typeof o === "object" && typeof o.label === "string")
    .map((o, idx) => ({
      id: String(o.id ?? `opt-${idx}`),
      label: o.label as string,
      description: typeof o.description === "string" ? o.description : "",
      actions: Array.isArray(o.actions)
        ? o.actions.filter((a): a is string => typeof a === "string")
        : undefined,
      confidence: typeof o.confidence === "number" ? o.confidence : undefined,
    }));
}

function makeProposalId(): string {
  return `prop-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function parseProposalContent(content: string): ProposalParseResult {
  const proposals: Proposal[] = [];
  let failedBlockCount = 0;
  let match: RegExpExecArray | null;

  PROPOSAL_RE.lastIndex = 0;
  while ((match = PROPOSAL_RE.exec(content)) !== null) {
    const raw = parseProposalJson(match[1]);
    if (!raw) {
      failedBlockCount += 1;
      continue;
    }
    const options = mapProposalOptions(raw.options);
    if (options.length === 0) {
      failedBlockCount += 1;
      continue;
    }
    proposals.push({
      id: makeProposalId(),
      title: typeof raw.title === "string" ? raw.title : "Choose an approach",
      options,
    });
  }

  return { proposals, failedBlockCount };
}

export function extractProposals(content: string): Proposal[] {
  return parseProposalContent(content).proposals;
}

export function stripProposalBlocks(content: string): string {
  return content.replace(PROPOSAL_RE, "").trim();
}

export function hasProposal(content: string): boolean {
  PROPOSAL_RE.lastIndex = 0;
  return PROPOSAL_RE.test(content);
}

export function formatOptionSelection(proposal: Proposal, option: ProposalOption): string {
  const lines = [
    `I'll go with: **${option.label}**`,
    "",
    option.description ? `> ${option.description}` : "",
    "",
    `<!--proposal-selected: ${proposal.id} / ${option.id}-->`,
  ];
  return lines.filter(Boolean).join("\n");
}
