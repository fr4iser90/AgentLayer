import type { AuthContextValue } from "../../../auth/AuthContext";
import { apiFetch } from "../../../lib/api";

function apiErrorDetail(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  return fallback;
}

async function readJsonResponse<T>(res: Response, fallback: string): Promise<T> {
  const text = await res.text();
  if (!text.trim()) {
    if (!res.ok) throw new Error(fallback);
    return {} as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(!res.ok ? fallback : "Invalid JSON response from server");
  }
}

export type HarnessPreset = "observability" | "chat_parity";

export type HarnessConfigFields = {
  harness_preset: HarnessPreset;
  max_tool_rounds_override?: number | null;
  scenario_timeout_sec?: number | null;
  capture_timeline?: boolean | null;
  stream_llm?: boolean | null;
  notes?: string | null;
};

export type HarnessGlobalConfig = HarnessConfigFields & {
  updated_at?: string | null;
  updated_by?: string | null;
};

export type HarnessModelOverride = HarnessConfigFields & {
  id: string;
  catalog_owned_by: string;
  model?: string | null;
  label?: string | null;
  scope?: string;
  updated_at?: string | null;
};

export type HarnessMatrixResponse = {
  global: HarnessGlobalConfig;
  overrides: HarnessModelOverride[];
};

export type HarnessOverrideBody = HarnessConfigFields & {
  catalog_owned_by: string;
  model?: string | null;
  label?: string | null;
};

export async function fetchHarnessMatrix(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">
): Promise<HarnessMatrixResponse> {
  const res = await apiFetch("/v1/admin/benchmark-harness", auth);
  const data = await readJsonResponse<HarnessMatrixResponse & { detail?: unknown }>(
    res,
    `Failed to load harness matrix (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data;
}

export async function saveHarnessGlobal(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  body: HarnessConfigFields
): Promise<HarnessGlobalConfig> {
  const res = await apiFetch("/v1/admin/benchmark-harness/global", auth, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await readJsonResponse<{ global?: HarnessGlobalConfig; detail?: unknown }>(
    res,
    `Failed to save global harness (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  return data.global ?? (body as HarnessGlobalConfig);
}

export async function createHarnessOverride(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  body: HarnessOverrideBody
): Promise<HarnessModelOverride> {
  const res = await apiFetch("/v1/admin/benchmark-harness/overrides", auth, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await readJsonResponse<{ override?: HarnessModelOverride; detail?: unknown }>(
    res,
    `Failed to create harness override (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  if (!data.override) throw new Error("Missing override in response");
  return data.override;
}

export async function updateHarnessOverride(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  overrideId: string,
  body: HarnessOverrideBody
): Promise<HarnessModelOverride> {
  const res = await apiFetch(`/v1/admin/benchmark-harness/overrides/${overrideId}`, auth, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await readJsonResponse<{ override?: HarnessModelOverride; detail?: unknown }>(
    res,
    `Failed to update harness override (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
  if (!data.override) throw new Error("Missing override in response");
  return data.override;
}

export async function deleteHarnessOverride(
  auth: Pick<AuthContextValue, "accessToken" | "refresh">,
  overrideId: string
): Promise<void> {
  const res = await apiFetch(`/v1/admin/benchmark-harness/overrides/${overrideId}`, auth, {
    method: "DELETE",
  });
  const data = await readJsonResponse<{ detail?: unknown }>(
    res,
    `Failed to delete harness override (HTTP ${res.status})`
  );
  if (!res.ok) throw new Error(apiErrorDetail(data, `HTTP ${res.status}`));
}
