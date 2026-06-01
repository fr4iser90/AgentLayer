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
  | "embed";

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

export interface UiBlock {
  id: string;
  type: BlockType;
  grid: GridPos;
  props: {
    dataPath?: string;
    columns?: ColumnDef[];
    placeholder?: string;
    /** gallery / hero section label */
    title?: string;
  };
}

export interface UiLayout {
  version: number;
  blocks: UiBlock[];
}

export interface DashboardSummary {
  id: string;
  kind: string;
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

export interface DashboardDetail extends DashboardSummary {
  ui_layout: UiLayout | Record<string, unknown>;
  /** Template payload; may include ``_agentlayer`` for AgentLayer agent settings. */
  data: Record<string, unknown>;
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
