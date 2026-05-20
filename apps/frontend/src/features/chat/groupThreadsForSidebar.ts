import type { ChatThread } from "./chatThreadStorage";

export type SidebarThreadGroup =
  | { kind: "source"; source: string; label: string; threads: ChatThread[] }
  | { kind: "dashboard"; dashboardId: string; label: string; threads: ChatThread[] };

export type BuildSidebarGroup = {
  workspaceId: string | null;
  label: string;
  threads: ChatThread[];
};

/** Registry ids for the Build / Coding Agent UI (not shown in general Chat sidebar). */
export const BUILD_AGENT_IDS = new Set(["coding", "coding_plan"]);

const byUpdated = (a: ChatThread, b: ChatThread) => b.updatedAt - a.updatedAt;

export function isBuildAgentThread(t: ChatThread): boolean {
  const aid = (t.agentId ?? "").trim().toLowerCase();
  return BUILD_AGENT_IDS.has(aid);
}

/** Threads with at least one message, or the currently open thread (empty draft sessions). */
export function threadsVisibleInSidebar(threads: ChatThread[], activeThreadId: string | null): ChatThread[] {
  return threads.filter(
    (t) => (t.messageCount ?? t.messages.length) > 0 || t.id === activeThreadId
  );
}

/** Chat sidebar: all sessions (single Chat UI; legacy Build threads included). */
export function filterThreadsForChatSidebar(threads: ChatThread[]): ChatThread[] {
  return threads;
}

/** Build page sidebar: only coding / coding_plan sessions. */
export function filterThreadsForBuildSidebar(threads: ChatThread[]): ChatThread[] {
  return threads.filter((t) => isBuildAgentThread(t));
}

/** Sidebar heading for a bridge ``source`` id (telegram, slack, …). */
export function labelForChatSource(source: string): string {
  const s = source.trim().toLowerCase();
  if (!s || s === "web") return "Web";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Groups first-party vs bridge vs dashboard threads for the chat sidebar.
 * Bridge sections are keyed by ``thread.source`` (any provider string from the API).
 */
export function buildSidebarGroups(
  threads: ChatThread[],
  dashboardTitles: Record<string, string>
): SidebarThreadGroup[] {
  const bySource = new Map<string, ChatThread[]>();
  const byWs = new Map<string, ChatThread[]>();

  for (const t of threads) {
    if (t.dashboardId) {
      const list = byWs.get(t.dashboardId) ?? [];
      list.push(t);
      byWs.set(t.dashboardId, list);
      continue;
    }
    const src = (t.source ?? "web").trim().toLowerCase() || "web";
    const list = bySource.get(src) ?? [];
    list.push(t);
    bySource.set(src, list);
  }

  const out: SidebarThreadGroup[] = [];

  const sourceKeys = [...bySource.keys()].sort((a, b) => {
    if (a === "web") return -1;
    if (b === "web") return 1;
    return a.localeCompare(b);
  });
  for (const source of sourceKeys) {
    const th = bySource.get(source);
    if (!th?.length) continue;
    th.sort(byUpdated);
    out.push({
      kind: "source",
      source,
      label: labelForChatSource(source),
      threads: th,
    });
  }

  const wsEntries = [...byWs.entries()].map(([wid, th]) => {
    th.sort(byUpdated);
    const titled = dashboardTitles[wid]?.trim();
    return {
      kind: "dashboard" as const,
      dashboardId: wid,
      label: titled || `Dashboard ${wid.slice(0, 8)}…`,
      threads: th,
    };
  });
  wsEntries.sort((a, b) => a.label.localeCompare(b.label));
  out.push(...wsEntries);

  return out;
}

/** Build page: group sessions by ``workspaceId`` (project), newest first within each group. */
export function buildBuildSidebarGroups(
  threads: ChatThread[],
  workspaceNames: Record<string, string>
): BuildSidebarGroup[] {
  const byWs = new Map<string | null, ChatThread[]>();

  for (const t of threads) {
    const wid = t.workspaceId?.trim() || null;
    const list = byWs.get(wid) ?? [];
    list.push(t);
    byWs.set(wid, list);
  }

  const entries: BuildSidebarGroup[] = [];
  for (const [workspaceId, th] of byWs.entries()) {
    th.sort(byUpdated);
    const label =
      workspaceId && workspaceNames[workspaceId]?.trim()
        ? workspaceNames[workspaceId].trim()
        : workspaceId
          ? `Project ${workspaceId.slice(0, 8)}…`
          : "No project";
    entries.push({ workspaceId, label, threads: th });
  }

  entries.sort((a, b) => {
    if (a.workspaceId === null) return 1;
    if (b.workspaceId === null) return -1;
    return a.label.localeCompare(b.label);
  });

  return entries;
}
