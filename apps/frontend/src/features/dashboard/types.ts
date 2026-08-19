export type BlockType =
  | "table"
  | "schedules"
  | "markdown"
  | "gallery"
  | "hero"
  | "timeline"
  | "stat"
  | "chart"
  | "sparkline"
  | "kanban"
  | "rich_markdown"
  | "embed"
  | "media_player"
  | "section"
  | "card_grid"
  | "dashboard_ref"
  | "share_widget"
  | "formula_calc";

export interface GridPos {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ColumnDef {
  field: string;
  kind: "checkbox" | "text" | "number" | "select";
  label: string;
  options?: string[];
}

/** Declarative stat recompute (backend ``data_compute``). */
export type StatComputeSpec = {
  op: "count" | "count_where" | "count_nonempty" | "sum";
  from?: string;
  source?: string;
  field?: string;
  where?: Array<{
    field: string;
    eq?: string;
    neq?: string;
    in?: string[];
    not_in?: string[];
    nonempty?: boolean;
    empty?: boolean;
  }>;
};

export interface UiBlock {
  id: string;
  type: BlockType;
  grid: GridPos;
  props: {
    dataPath?: string;
    columns?: ColumnDef[];
    placeholder?: string;
    /** gallery / hero / section label */
    title?: string;
    /** gallery: columns at large breakpoints (2–5, default 3) */
    galleryColumns?: number;
    /** gallery: tile aspect ratio */
    galleryAspect?: "square" | "video" | "auto";
    /** section: nested grid layout (max depth 2) */
    nested?: UiLayout;
    /** section: hide inner grid when true */
    collapsed?: boolean;
    /** table and projects-specific props — see DashboardBlocks */
    [key: string]: unknown;
  };
}

export interface UiLayout {
  version: 1 | 2;
  blocks: UiBlock[];
}

export interface DashboardSummary {
  id: string;
  kind: string;
  /** Gallery template used at create time (e.g. projects-v1); null for legacy/custom. */
  template_id?: string | null;
  title: string;
  updated_at: string;
  created_at: string;
  /** owner | editor | viewer — absent on older APIs (treat as owner) */
  access_role?: string;
}

/** Reserved namespace inside dashboard ``data`` (JSON). Safe alongside template-specific keys. */
export type DashboardDataAgentlayer = {
  /** Appended to the server system prompt when this dashboard is active (embedded + API with context). */
  system_prompt_extra?: string;
  /** Alias for ``system_prompt_extra`` (same behavior). */
  instructions?: string;
  /**
   * If non-empty: only these OpenAI tool function names are forwarded for this dashboard
   * (after routing/policy/client disabled-tools). Empty/unset = no extra restriction.
   */
  tool_allowlist?: string[];
  /** Alias for ``tool_allowlist``. */
  allowed_tools?: string[];
};

export interface DashboardOnboardingStep {
  id: string;
  label: string;
  tool_hint?: string;
}

export interface DashboardOnboarding {
  version?: number;
  kind?: string;
  greeting: string;
  agent_prompt?: string;
  steps?: DashboardOnboardingStep[];
  suggested_tools?: string[];
  chat_starters?: string[];
}

export interface DashboardDetail extends DashboardSummary {
  ui_layout: UiLayout | Record<string, unknown>;
  /** Template payload; may include ``_agentlayer`` for AgentLayer agent settings. */
  data: Record<string, unknown>;
  /** Kind-specific setup manifest (computed server-side). */
  onboarding?: DashboardOnboarding;
  /** ``public`` on token-based shared views. */
  access_scope?: "full" | "granular" | "public";
  /** Label set by owner when creating a public share link. */
  share_label?: string;
  allowed_block_ids?: string[];
  /** True when the granular grant has ``edit`` (can PATCH shared blocks); omitted for full members. */
  granular_can_write?: boolean;
}

export interface DashboardMemberRow {
  user_id: string;
  email: string;
  role: string;
  created_at: string | null;
}

export interface DashboardBlockGrantRow {
  user_id: string;
  email: string;
  block_ids: string[];
  /** ``view`` = read-only blocks; ``edit`` = can update content/layout for shared blocks only. */
  permission?: "view" | "edit";
  created_at: string;
}

export interface DashboardPublicShareRow {
  id: string;
  label: string;
  block_ids: string[];
  /** ``full`` = entire dashboard; ``blocks`` = subset only */
  scope: "full" | "blocks";
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  password_protected?: boolean;
  url_path?: string;
}
