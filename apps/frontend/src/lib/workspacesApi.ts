import type { AuthContextValue } from "../auth/AuthContext";
import {
  apiFetch,
  type WorkspaceApiRecord,
  type WorkspaceListResponse,
  type WorkspaceListScope,
} from "./api";

export async function fetchWorkspacesApi(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  scope: WorkspaceListScope = "mine"
): Promise<WorkspaceListResponse> {
  const r = await apiFetch(`/v1/workspaces?scope=${scope}`, auth);
  if (!r.ok) {
    const err = (await r.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      typeof err.detail === "string" ? err.detail : `Failed to list workspaces (${r.status})`
    );
  }
  return (await r.json()) as WorkspaceListResponse;
}

export async function deleteWorkspaceApi(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  workspaceId: string
): Promise<void> {
  const r = await apiFetch(`/v1/workspaces/${encodeURIComponent(workspaceId)}`, auth, {
    method: "DELETE",
  });
  if (!r.ok) {
    const err = (await r.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      typeof err.detail === "string" ? err.detail : `Failed to delete workspace (${r.status})`
    );
  }
}

export function isAgentlayerSelfWorkspace(ws: Pick<WorkspaceApiRecord, "name">): boolean {
  return (ws.name || "").trim() === "agentlayer-self";
}
