import type { AuthContextValue } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import type { UiLayout } from "./types";

export type LayoutProposalRow = {
  id: string;
  title: string;
  summary: string;
  ui_layout: UiLayout;
};

export type LayoutProposalSet = {
  set_id: string;
  dashboard_id: string;
  proposals: LayoutProposalRow[];
};

export function asUiLayout(raw: unknown): UiLayout | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as { version?: number; blocks?: unknown };
  if (!Array.isArray(o.blocks)) return null;
  return { version: Number(o.version) || 1, blocks: o.blocks as UiLayout["blocks"] };
}

export function normalizeProposalSet(raw: unknown): LayoutProposalSet | null {
  if (!raw || typeof raw !== "object") return null;
  const ps = raw as {
    set_id?: string;
    dashboard_id?: string;
    proposals?: Array<{
      id?: string;
      title?: string;
      summary?: string;
      ui_layout?: unknown;
    }>;
  };
  if (!ps.set_id || !Array.isArray(ps.proposals)) return null;
  const proposals: LayoutProposalRow[] = [];
  for (const p of ps.proposals) {
    const ul = asUiLayout(p.ui_layout);
    if (!ul) continue;
    proposals.push({
      id: String(p.id || "").trim() || `prop_${proposals.length}`,
      title: String(p.title || "").trim() || `Option ${proposals.length + 1}`,
      summary: String(p.summary || "").trim(),
      ui_layout: ul,
    });
  }
  if (!proposals.length) return null;
  return {
    set_id: ps.set_id,
    dashboard_id: String(ps.dashboard_id || ""),
    proposals,
  };
}

export async function fetchLayoutProposalSet(
  auth: AuthContextValue,
  dashboardId: string,
  setId: string
): Promise<LayoutProposalSet | null> {
  const res = await apiFetch(
    `/v1/dashboards/${dashboardId}/layout-proposals/${encodeURIComponent(setId)}`,
    auth
  );
  if (!res.ok) return null;
  const j = (await res.json()) as { proposal_set?: unknown };
  return normalizeProposalSet(j.proposal_set);
}

export async function fetchActiveLayoutProposalSet(
  auth: AuthContextValue,
  dashboardId: string
): Promise<LayoutProposalSet | null> {
  const res = await apiFetch(`/v1/dashboards/${dashboardId}/layout-proposals/active`, auth);
  if (!res.ok) return null;
  const j = (await res.json()) as { proposal_set?: unknown };
  if (!j.proposal_set) return null;
  return normalizeProposalSet(j.proposal_set);
}

export async function applyLayoutProposal(
  auth: AuthContextValue,
  dashboardId: string,
  setId: string,
  proposalId: string
): Promise<{ ok: true } | { ok: false; error: string }> {
  const res = await apiFetch(
    `/v1/dashboards/${dashboardId}/layout-proposals/${encodeURIComponent(setId)}/${encodeURIComponent(proposalId)}/apply`,
    auth,
    { method: "POST" }
  );
  if (!res.ok) {
    return { ok: false, error: await res.text() };
  }
  return { ok: true };
}
