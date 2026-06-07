import type { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { getPath, setPath } from "../dashboard/dashboardDataPaths";
import { readQueue, type MediaQueueState, type MediaSessionBinding } from "./mediaTypes";

type Auth = ReturnType<typeof useAuth>;

const BINDING_STORAGE_KEY = "agentlayer:media-dashboard-binding";

type DashboardRow = {
  id: string;
  kind?: string;
  title?: string;
  access_role?: string;
  ui_layout?: unknown;
};

type DashboardDetail = {
  id: string;
  title?: string;
  kind?: string;
  data?: Record<string, unknown>;
  ui_layout?: unknown;
  access_role?: string;
};

const WRITABLE_ROLES = new Set(["owner", "co_owner", "editor"]);

function mediaQueuePathsFromLayout(ul: unknown): string[] {
  if (!ul || typeof ul !== "object") return ["media_queue"];
  const layout = ul as { blocks?: unknown[] };
  const blocks = Array.isArray(layout.blocks) ? layout.blocks : [];
  const paths: string[] = [];
  for (const b of blocks) {
    if (!b || typeof b !== "object") continue;
    const block = b as { type?: string; props?: { dataPath?: string } };
    if (String(block.type || "").toLowerCase() !== "media_player") continue;
    const dp = String(block.props?.dataPath || "media_queue").trim() || "media_queue";
    if (!paths.includes(dp)) paths.push(dp);
  }
  return paths.length ? paths : ["media_queue"];
}

function readStoredBinding(): MediaSessionBinding | null {
  try {
    const raw = localStorage.getItem(BINDING_STORAGE_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as MediaSessionBinding;
    if (!o.dashboardId?.trim() || !o.dataPath?.trim()) return null;
    return {
      dashboardId: o.dashboardId.trim(),
      dataPath: o.dataPath.trim(),
      dashboardTitle: o.dashboardTitle?.trim() || undefined,
    };
  } catch {
    return null;
  }
}

export function writeStoredBinding(binding: MediaSessionBinding | null): void {
  try {
    if (!binding) {
      localStorage.removeItem(BINDING_STORAGE_KEY);
      return;
    }
    localStorage.setItem(BINDING_STORAGE_KEY, JSON.stringify(binding));
  } catch {
    /* ignore */
  }
}

function pickDashboard(rows: DashboardRow[]): DashboardRow | null {
  const writable = rows.filter((r) => WRITABLE_ROLES.has(String(r.access_role || "owner")));
  if (!writable.length) return null;
  const stored = readStoredBinding();
  if (stored) {
    const hit = writable.find((r) => r.id === stored.dashboardId);
    if (hit) return hit;
  }
  const mediaStation = writable.filter((r) => (r.kind || "").trim() === "media_station");
  if (mediaStation.length === 1) return mediaStation[0] ?? null;
  const personal = writable.filter((r) => (r.kind || "").trim() === "personal_dashboard");
  if (personal.length === 1) return personal[0] ?? null;
  return writable[0] ?? null;
}

export async function resolveMediaSessionBinding(
  auth: Auth
): Promise<MediaSessionBinding | null> {
  try {
    const res = await apiFetch("/v1/dashboards", auth);
    if (!res.ok) return null;
    const j = (await res.json()) as { dashboards?: DashboardRow[] };
    const rows = Array.isArray(j.dashboards) ? j.dashboards : [];
    const pick = pickDashboard(rows);
    if (!pick?.id) return null;
    const stored = readStoredBinding();
    const queuePath =
      stored?.dashboardId === pick.id
        ? stored.dataPath
        : mediaQueuePathsFromLayout(pick.ui_layout)[0] ?? "media_queue";
    const binding: MediaSessionBinding = {
      dashboardId: pick.id,
      dataPath: queuePath,
      dashboardTitle: pick.title?.trim() || undefined,
    };
    writeStoredBinding(binding);
    return binding;
  } catch {
    return null;
  }
}

export async function loadQueueForBinding(
  auth: Auth,
  binding: MediaSessionBinding
): Promise<MediaQueueState> {
  try {
    const res = await apiFetch(`/v1/dashboards/${encodeURIComponent(binding.dashboardId)}`, auth);
    if (!res.ok) return readQueue(undefined);
    const j = (await res.json()) as { dashboard?: DashboardDetail };
    const data = j.dashboard?.data;
    if (!data || typeof data !== "object") return readQueue(undefined);
    return readQueue(getPath(data, binding.dataPath));
  } catch {
    return readQueue(undefined);
  }
}

export async function persistQueueForBinding(
  auth: Auth,
  binding: MediaSessionBinding,
  queue: MediaQueueState
): Promise<boolean> {
  try {
    const res = await apiFetch(`/v1/dashboards/${encodeURIComponent(binding.dashboardId)}`, auth);
    if (!res.ok) return false;
    const j = (await res.json()) as { dashboard?: DashboardDetail };
    const dash = j.dashboard;
    if (!dash) return false;
    const role = dash.access_role || "owner";
    if (!WRITABLE_ROLES.has(role)) return false;
    const data =
      dash.data && typeof dash.data === "object" ? { ...dash.data } : ({} as Record<string, unknown>);
    const newData = setPath(data, binding.dataPath, queue);
    const patch = await apiFetch(`/v1/dashboards/${encodeURIComponent(binding.dashboardId)}`, auth, {
      method: "PATCH",
      body: JSON.stringify({ data: newData }),
    });
    return patch.ok;
  } catch {
    return false;
  }
}
