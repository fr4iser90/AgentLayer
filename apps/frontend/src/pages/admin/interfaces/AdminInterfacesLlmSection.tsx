import { useOperatorSettings } from "../../../features/admin/operatorSettings/OperatorSettingsProvider";
import {
  envProviderPatternFromCleanupKeys,
  type OperatorEnvProviderPreview,
  type OperatorProviderEndpointUI,
  type OperatorProviderKindMetadata,
} from "../../../features/admin/operatorSettings/operatorSettingsTypes";
import { useTranslation } from "react-i18next";
import {
  modelCapabilityBadges,
  type ModelRow,
} from "../../../lib/modelCatalog";
import { apiFetch } from "../../../lib/api";
import { useAuth } from "../../../auth/AuthContext";
import { hasOrgSurface } from "../../../auth/deploymentMode";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../../../ui/Button";

type AdminModelCatalogPref = {
  provider_id?: string;
  model_id?: string;
  visible_in_chat?: boolean;
};

type AccessScope = "global" | "tenant" | "user";
type AccessState = "inherit" | "allow" | "deny";
type ModelProfile = "default" | "agent" | "coding" | "vlm" | "embedding" | "extractor" | "stt" | "tts";
type ProviderCapability = "chat" | "embedding" | "extractor" | "stt" | "tts" | "voice_realtime";

type TenantRow = { id: number; name?: string | null };
type UserRow = {
  id: string;
  email?: string | null;
  display_name?: string | null;
  external_sub?: string | null;
  tenant_id?: number;
};

type ModelAccessPolicyRow = {
  provider_id?: string;
  model_id?: string;
  access_state?: AccessState;
  sort_order?: number;
};

type ModelDefaultPolicyRow = {
  profile?: ModelProfile;
  provider_id?: string;
  model_id?: string;
};

type ProviderCapabilityPolicyRow = {
  capability?: ProviderCapability;
  provider_id?: string;
  access_state?: AccessState;
};

type ModelAccessPayload = {
  default_model_access_state?: AccessState;
  default_provider_capability_state?: AccessState;
  model_access?: ModelAccessPolicyRow[];
  model_defaults?: ModelDefaultPolicyRow[];
  provider_capabilities?: ProviderCapabilityPolicyRow[];
  detail?: unknown;
};

type CapabilityProviderCard = {
  capability: ProviderCapability;
  providerKind?: string;
  metadata?: OperatorProviderKindMetadata;
  providerId: string;
  label: string;
  source?: string;
  baseUrl?: string;
  meta?: string | null;
  models?: string[];
};

type ModelAccessProviderGroup = {
  providerId: string;
  label: string;
  source?: string;
  endpointId?: number | null;
  profileSource?: {
    modelDefault?: string | null;
    modelVlm?: string | null;
    modelAgent?: string | null;
    modelCoding?: string | null;
  };
  rows: ModelRow[];
};

function isProviderCapability(value: string): value is ProviderCapability {
  return ["chat", "embedding", "extractor", "stt", "tts", "voice_realtime"].includes(value);
}

function isModelProfile(value: string): value is ModelProfile {
  return ["default", "agent", "coding", "vlm", "embedding", "extractor", "stt", "tts"].includes(value);
}

async function fetchAdminTenants(auth: Parameters<typeof apiFetch>[1]): Promise<TenantRow[]> {
  const res = await apiFetch("/v1/admin/tenants", auth);
  const data = (await res.json().catch(() => ({}))) as { tenants?: TenantRow[] };
  if (!res.ok) return [];
  return Array.isArray(data.tenants) ? data.tenants : [];
}

async function fetchAdminUsers(auth: Parameters<typeof apiFetch>[1]): Promise<UserRow[]> {
  const res = await apiFetch("/v1/admin/users", auth);
  const data = (await res.json().catch(() => ({}))) as { users?: UserRow[] };
  if (!res.ok) return [];
  return Array.isArray(data.users) ? data.users : [];
}

async function fetchAdminModelCatalog(
  auth: Parameters<typeof apiFetch>[1]
): Promise<{ rows: ModelRow[]; prefs: AdminModelCatalogPref[] }> {
  const res = await apiFetch("/v1/admin/model-catalog", auth);
  const data = (await res.json().catch(() => ({}))) as {
    data?: ModelRow[];
    prefs?: AdminModelCatalogPref[];
  };
  if (!res.ok) return { rows: [], prefs: [] };
  return {
    rows: Array.isArray(data.data) ? data.data : [],
    prefs: Array.isArray(data.prefs) ? data.prefs : [],
  };
}

function profileBadgesForModel(
  provider: {
    modelDefault?: string | null;
    modelVlm?: string | null;
    modelAgent?: string | null;
    modelCoding?: string | null;
  },
  modelId: string,
): string[] {
  const id = modelId.trim();
  const badges: string[] = [];
  if (id && provider.modelDefault?.trim() === id) badges.push("Default");
  if (id && provider.modelAgent?.trim() === id) badges.push("Agent");
  if (id && provider.modelCoding?.trim() === id) badges.push("Coding");
  if (id && provider.modelVlm?.trim() === id) badges.push("VLM");
  return badges;
}

function modelAccessKey(providerId: string, modelId: string): string {
  return `${providerId.trim().toLowerCase()}:${modelId.trim()}`;
}

function capabilityAccessKey(capability: ProviderCapability, providerId: string): string {
  return `${capability}:${providerId.trim().toLowerCase()}`;
}

function policyEndpoint(scope: AccessScope, tenantId: string, userId: string): string | null {
  if (scope === "global") return "/v1/admin/model-access/global";
  if (scope === "tenant") {
    const id = tenantId.trim();
    return id ? `/v1/admin/model-access/tenants/${encodeURIComponent(id)}` : null;
  }
  const id = userId.trim();
  return id ? `/v1/admin/model-access/users/${encodeURIComponent(id)}` : null;
}

function validAccessState(value: unknown): AccessState {
  return value === "allow" || value === "deny" || value === "inherit" ? value : "inherit";
}

function userLabel(row: UserRow): string {
  return (row.email ?? "").trim() || (row.display_name ?? "").trim() || (row.external_sub ?? "").trim() || row.id;
}

function tenantLabel(row: TenantRow, fallback: string): string {
  const name = (row.name ?? "").trim();
  return name ? `${name} (${row.id})` : `${fallback} ${row.id}`;
}

function uniqueCapabilityProviders(rows: CapabilityProviderCard[]): CapabilityProviderCard[] {
  const seen = new Set<string>();
  const out: CapabilityProviderCard[] = [];
  for (const row of rows) {
    const providerId = row.providerId.trim().toLowerCase();
    if (!providerId) continue;
    const key = capabilityAccessKey(row.capability, providerId);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ ...row, providerId });
  }
  return out;
}

function ProviderModelSelect({
  id,
  value,
  models,
  onChange,
  placeholder,
}: {
  id: string;
  value: string;
  models: string[];
  onChange: (value: string) => void;
  placeholder: string;
}) {
  const current = value.trim();
  const options = current && !models.includes(current) ? [current, ...models] : models;
  return (
    <select
      id={id}
      className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary disabled:opacity-50"
      value={current}
      disabled={options.length === 0}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" disabled hidden>
        {placeholder}
      </option>
      {options.map((model) => (
        <option key={model} value={model}>
          {model}
        </option>
      ))}
    </select>
  );
}

function AccessStateControl({
  value,
  onChange,
  labels,
}: {
  value: AccessState;
  onChange: (value: AccessState) => void;
  labels: Record<AccessState, string>;
}) {
  const states: AccessState[] = ["inherit", "allow", "deny"];
  return (
    <div className="flex shrink-0 overflow-hidden rounded-tile border border-line bg-black/30 text-xs">
      {states.map((state) => (
        <button
          key={state}
          type="button"
          className={`px-base py-tight ${
            value === state
              ? state === "allow"
                ? "bg-emerald-500/25 text-emerald-100"
                : state === "deny"
                  ? "bg-danger-subtle text-badge-danger"
                  : "bg-white/15 text-ink-primary"
              : "text-ink-secondary hover:bg-white/10"
          }`}
          onClick={() => onChange(state)}
        >
          {labels[state]}
        </button>
      ))}
    </div>
  );
}

export function AdminInterfacesLlmSection({
  mode = "all",
}: {
  mode?: "all" | "providers" | "policies" | "routing";
}) {
  const { t } = useTranslation(["admin"]);
  const s = useOperatorSettings();
  const auth = useAuth();
  const adminText = (key: string | null | undefined, fallback = ""): string => {
    if (!key) return fallback;
    return String(t(`admin:${key}` as never, { defaultValue: fallback || key } as never));
  };
  const [catalogRows, setCatalogRows] = useState<ModelRow[]>([]);
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [accessScope, setAccessScope] = useState<AccessScope>("global");
  const [accessTenantId, setAccessTenantId] = useState("1");
  // Tenant-scoped model access is a tenant-selection surface: with no org surface
  // there is one tenant and nothing to scope against, so the option is not offered.
  const showTenantScope = hasOrgSurface(auth.user);
  const [accessUserId, setAccessUserId] = useState("");
  const [modelAccess, setModelAccess] = useState<Record<string, AccessState>>({});
  const [modelDefaults, setModelDefaults] = useState<Record<ModelProfile, string>>({
    default: "",
    agent: "",
    coding: "",
    vlm: "",
    embedding: "",
    extractor: "",
    stt: "",
    tts: "",
  });
  const [capabilityAccess, setCapabilityAccess] = useState<Record<string, AccessState>>({});
  const [defaultModelAccessState, setDefaultModelAccessState] = useState<AccessState>("inherit");
  const [defaultProviderCapabilityState, setDefaultProviderCapabilityState] = useState<AccessState>("inherit");
  const [policyLoading, setPolicyLoading] = useState(false);
  const [policySaving, setPolicySaving] = useState(false);
  const [policyMsg, setPolicyMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const policyRequestRef = useRef<{ key: string; requestId: number }>({ key: "", requestId: 0 });
  const showProviders = mode === "all" || mode === "providers";
  const showPolicies = mode === "all" || mode === "policies";
  const showRouting = mode === "all" || mode === "routing";
  const effectiveCatalogRows = catalogRows.length ? catalogRows : s.modelCatalogRows;
  const operatorEnvImportGroups = useMemo(
    () => {
      const grouped = new Map<string, OperatorEnvProviderPreview[]>();
      for (const provider of Object.values(s.envOperatorProviders).flat()) {
        if (provider.already_in_db) continue;
        const rows = grouped.get(provider.kind) ?? [];
        rows.push(provider);
        grouped.set(provider.kind, rows);
      }
      const metadataByKind = new Map(s.operatorProviderKindMetadata.map((metadata) => [metadata.kind, metadata]));
      return [...grouped.entries()].map(([kind, providers]) => ({
        kind,
        envPrefix:
          metadataByKind.get(kind)?.env_prefix_pattern ??
          envProviderPatternFromCleanupKeys(providers[0]?.cleanup_keys),
        providers,
      }));
    },
    [s.envOperatorProviders, s.operatorProviderKindMetadata]
  );
  const operatorDbEndpointGroups = useMemo(
    () =>
      s.operatorProviderKindMetadata
        .map((metadata) => ({
          kind: metadata.kind,
          metadata,
          title: adminText(metadata.title_i18n_key, metadata.kind),
          intro: adminText(metadata.intro_i18n_key),
          endpoints: s.operatorProviderEndpoints[metadata.kind] ?? [],
        })),
    [s.operatorProviderEndpoints, s.operatorProviderKindMetadata, t]
  );
  const modelOptions = effectiveCatalogRows
    .map((row) => {
      const providerId = (row.owned_by ?? "").trim().toLowerCase();
      const modelId = row.id.trim();
      return providerId && modelId ? { providerId, modelId, value: `${providerId}:${modelId}` } : null;
    })
    .filter((row): row is { providerId: string; modelId: string; value: string } => row !== null);
  const genericAccessProviderGroups = useMemo(() => {
    return s.operatorProviderKindMetadata
      .filter((metadata) => isProviderCapability(metadata.capability))
      .map((metadata) => {
        const capability = metadata.capability as ProviderCapability;
        const endpoints = s.operatorProviderEndpoints[metadata.kind] ?? [];
        return {
          id: metadata.kind,
          title: adminText(metadata.title_i18n_key, metadata.kind),
          intro: adminText(metadata.intro_i18n_key),
          empty: adminText(metadata.empty_i18n_key),
          providers: uniqueCapabilityProviders(
            endpoints
              .filter((endpoint) => endpoint.enabled !== false)
              .map((endpoint) => {
                const providerId = operatorEndpointProviderId(endpoint);
                return {
                  capability,
                  providerId,
                  label: endpoint.label || endpoint.baseUrl || providerId,
                  source: endpoint.source || "db",
                  baseUrl: endpoint.baseUrl,
                  meta: endpoint.modelDefault ? `${adminText(metadata.model_label_i18n_key, "Model")}: ${endpoint.modelDefault}` : null,
                  models: endpoint.models,
                  providerKind: metadata.kind,
                  metadata,
                };
              })
              .filter((provider) => provider.providerId)
          ),
        };
      });
  }, [
    s.operatorProviderEndpoints,
    s.operatorProviderKindMetadata,
    t,
  ]);
  const accessProviderGroups = useMemo(
    () => genericAccessProviderGroups,
    [genericAccessProviderGroups]
  );
  const capabilityProviders = useMemo(
    () => accessProviderGroups.flatMap((group) => group.providers),
    [accessProviderGroups]
  );

  const modelAccessProviderGroups = useMemo<ModelAccessProviderGroup[]>(() => {
    const groups: ModelAccessProviderGroup[] = [];
    for (const provider of capabilityProviders) {
      if (!provider.providerKind || !provider.metadata?.supports_models) continue;
      const key = s.operatorProviderModelKey(provider.providerKind, provider.providerId);
      const modelIds = (provider.models && provider.models.length > 0)
        ? provider.models
        : (s.operatorProviderModelOptions[key] ?? []);
      if (modelIds.length === 0) continue;
      groups.push({
        providerId: provider.providerId,
        label: provider.label,
        source: provider.source,
        endpointId: null,
        rows: [...new Set(modelIds)]
          .sort((a, b) => a.localeCompare(b))
          .map((modelId) => ({
            id: modelId,
            owned_by: provider.providerId,
            capabilities: {
              input_modalities:
                provider.capability === "stt"
                  ? ["audio"]
                  : provider.capability === "chat" || provider.capability === "embedding" || provider.capability === "extractor"
                    ? ["text"]
                    : undefined,
              output_modalities:
                provider.capability === "tts"
                  ? ["audio"]
                  : provider.capability === "chat" || provider.capability === "embedding" || provider.capability === "extractor"
                    ? ["text"]
                    : undefined,
            },
          })),
      });
    }
    return groups;
  }, [
    capabilityProviders,
    s.operatorProviderModelKey,
    s.operatorProviderModelOptions,
  ]);

  useEffect(() => {
    const requested = new Set<string>();
    for (const group of operatorDbEndpointGroups) {
      if (!group.metadata.supports_models) continue;
      for (const endpoint of group.endpoints) {
        const providerId = operatorEndpointProviderId(endpoint);
        const key = `${group.kind}:${providerId}`;
        if (providerId && !requested.has(key)) {
          requested.add(key);
          void s.loadOperatorProviderModels(group.kind, providerId);
        }
      }
    }
    for (const provider of capabilityProviders) {
      if (!provider.providerKind || !provider.metadata?.supports_models) continue;
      const key = `${provider.providerKind}:${provider.providerId}`;
      if (!requested.has(key)) {
        requested.add(key);
        void s.loadOperatorProviderModels(provider.providerKind, provider.providerId);
      }
    }
  }, [capabilityProviders, operatorDbEndpointGroups, s.loadOperatorProviderModels]);

  const nonChatRuntimeModelDefaults = s.operatorProviderKindMetadata.reduce<
    Array<{
      metadata: OperatorProviderKindMetadata;
      profile: ModelProfile;
      models: Array<{ value: string; label: string }>;
    }>
  >((rows, metadata) => {
      if (!metadata.supports_models || metadata.capability === "chat") return rows;
      const profile = metadata.capability as ModelProfile;
      const providers = capabilityProviders.filter((provider) => provider.providerKind === metadata.kind);
      const seen = new Set<string>();
      const models = providers
        .flatMap((provider) => {
          const key = s.operatorProviderModelKey(metadata.kind, provider.providerId);
          const modelIds = provider.models && provider.models.length > 0
            ? provider.models
            : (s.operatorProviderModelOptions[key] ?? []);
          return modelIds.map((modelId) => ({
            value: `${provider.providerId}:${modelId}`,
            label: `${provider.label}: ${modelId}`,
          }));
        })
        .filter((row) => {
          if (seen.has(row.value)) return false;
          seen.add(row.value);
          return true;
        })
        .sort((a, b) => a.label.localeCompare(b.label));
      rows.push({ metadata, profile, models });
      return rows;
    }, []);

  const catalogRuntimeModelDefaults = s.modelDefaultProfileMetadata
    .filter((metadata) => metadata.source === "catalog" && isModelProfile(metadata.profile))
    .map((metadata) => ({
      metadata,
      profile: metadata.profile as ModelProfile,
    }));

  function addOperatorEndpoint(kind: string) {
    s.setOperatorProviderEndpoints((prev) => ({
      ...prev,
      [kind]: [
        ...(prev[kind] ?? []),
        {
          id: null,
          kind,
          providerId: "",
          source: "db",
          enabled: true,
          label: "",
          baseUrl: "",
          apiKey: "",
          apiKeyConfigured: false,
          apiHeaderName: "Authorization",
          modelDefault: "",
          maxParallel: 1,
          optionsJson: {},
          models: [],
          modelsDetail: null,
        },
      ],
    }));
  }

  function updateOperatorEndpoint(kind: string, idx: number, patch: Partial<OperatorProviderEndpointUI>) {
    s.setOperatorProviderEndpoints((prev) => ({
      ...prev,
      [kind]: (prev[kind] ?? []).map((row, rowIdx) => (rowIdx === idx ? { ...row, ...patch } : row)),
    }));
  }

  function removeOperatorEndpoint(kind: string, idx: number) {
    const endpoint = s.operatorProviderEndpoints[kind]?.[idx];
    if (endpoint?.id != null) {
      s.setOperatorProviderDeleteIds((prev) => ({
        ...prev,
        [kind]: [...new Set([...(prev[kind] ?? []), endpoint.id as number])],
      }));
    }
    s.setOperatorProviderEndpoints((prev) => ({
      ...prev,
      [kind]: (prev[kind] ?? []).filter((_, rowIdx) => rowIdx !== idx),
    }));
  }

  function operatorEndpointProviderId(endpoint: OperatorProviderEndpointUI): string {
    if (endpoint.providerId.trim()) return endpoint.providerId.trim();
    return endpoint.label || endpoint.baseUrl;
  }

  useEffect(() => {
    let cancelled = false;
    const refreshAdminCatalog = async () => {
      try {
        const [catalog, tenantRows, userRows] = await Promise.all([
          fetchAdminModelCatalog(auth),
          fetchAdminTenants(auth),
          fetchAdminUsers(auth),
        ]);
        if (cancelled) return;
        setTenants(tenantRows);
        setUsers(userRows);
        setAccessTenantId((prev) => (tenantRows.some((row) => String(row.id) === prev) ? prev : String(tenantRows[0]?.id ?? 1)));
        setAccessUserId((prev) => (prev && userRows.some((row) => row.id === prev) ? prev : userRows[0]?.id ?? ""));
        setCatalogRows(catalog.rows);
        s.setModelCatalogRows(catalog.rows);
        const prefMap: Record<string, boolean> = {};
        for (const row of catalog.rows) {
          const providerId = (row.owned_by ?? "").trim().toLowerCase();
          const modelId = row.id.trim();
          if (providerId && modelId) {
            prefMap[s.modelPrefKey(providerId, modelId)] = true;
          }
        }
        for (const pref of catalog.prefs) {
          const providerId = (pref.provider_id ?? "").trim().toLowerCase();
          const modelId = (pref.model_id ?? "").trim();
          if (providerId && modelId) {
            prefMap[s.modelPrefKey(providerId, modelId)] = pref.visible_in_chat !== false;
          }
        }
        s.setModelCatalogPrefs(prefMap);
      } catch {
        if (cancelled) return;
        setCatalogRows([]);
      }
    };
    void refreshAdminCatalog();
    const onProviderCatalogChanged = () => {
      void refreshAdminCatalog();
    };
    window.addEventListener("agentlayer:provider-catalog-changed", onProviderCatalogChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("agentlayer:provider-catalog-changed", onProviderCatalogChanged);
    };
  }, [auth, s.modelPrefKey, s.setModelCatalogPrefs, s.setModelCatalogRows]);

  useEffect(() => {
    if (!showPolicies) return;
    const endpoint = policyEndpoint(accessScope, accessTenantId, accessUserId);
    if (!endpoint) return;
    if (policyRequestRef.current.key === endpoint) return;
    const requestId = policyRequestRef.current.requestId + 1;
    policyRequestRef.current = { key: endpoint, requestId };
    let cancelled = false;
    setPolicyLoading(true);
    setPolicyMsg(null);
    void (async () => {
      try {
        const res = await apiFetch(endpoint, auth);
        const data = (await res.json().catch(() => ({}))) as ModelAccessPayload;
        if (cancelled || policyRequestRef.current.requestId !== requestId) return;
        if (!res.ok) {
          setPolicyMsg({ ok: false, text: t("admin:modelAccessLoadFailed") });
          return;
        }
        setDefaultModelAccessState(validAccessState(data.default_model_access_state));
        setDefaultProviderCapabilityState(validAccessState(data.default_provider_capability_state));
        const nextAccess: Record<string, AccessState> = {};
        for (const row of data.model_access ?? []) {
          const providerId = (row.provider_id ?? "").trim().toLowerCase();
          const modelId = (row.model_id ?? "").trim();
          if (providerId && modelId) {
            nextAccess[modelAccessKey(providerId, modelId)] = validAccessState(row.access_state);
          }
        }
        const nextDefaults: Record<ModelProfile, string> = {
          default: "",
          agent: "",
          coding: "",
          vlm: "",
          embedding: "",
          extractor: "",
          stt: "",
          tts: "",
        };
        for (const row of data.model_defaults ?? []) {
          const profile = row.profile;
          const providerId = (row.provider_id ?? "").trim().toLowerCase();
          const modelId = (row.model_id ?? "").trim();
          if (profile && providerId && modelId) {
            nextDefaults[profile] = `${providerId}:${modelId}`;
          }
        }
        const nextCaps: Record<string, AccessState> = {};
        for (const row of data.provider_capabilities ?? []) {
          const capability = row.capability;
          const providerId = (row.provider_id ?? "").trim().toLowerCase();
          if (capability && providerId) {
            nextCaps[capabilityAccessKey(capability, providerId)] = validAccessState(row.access_state);
          }
        }
        setModelAccess(nextAccess);
        setModelDefaults(nextDefaults);
        setCapabilityAccess(nextCaps);
      } catch {
        if (!cancelled && policyRequestRef.current.requestId === requestId) {
          setPolicyMsg({ ok: false, text: t("admin:modelAccessLoadFailed") });
        }
      } finally {
        if (!cancelled && policyRequestRef.current.requestId === requestId) setPolicyLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    accessScope,
    accessTenantId,
    accessUserId,
    auth,
    showPolicies,
    t,
  ]);

  async function saveModelAccessPolicy() {
    const endpoint = policyEndpoint(accessScope, accessTenantId, accessUserId);
    if (!endpoint) {
      setPolicyMsg({ ok: false, text: t("admin:modelAccessSelectScope") });
      return false;
    }
    setPolicySaving(true);
    setPolicyMsg(null);
    try {
      const model_access = modelAccessProviderGroups
        .flatMap((group) =>
          group.rows.map((row) => ({
            providerId: (row.owned_by ?? group.providerId).trim().toLowerCase(),
            modelId: row.id.trim(),
          }))
        )
        .map((row, idx) => {
          if (!row.providerId || !row.modelId) return null;
          return {
            provider_id: row.providerId,
            model_id: row.modelId,
            access_state:
              modelAccess[modelAccessKey(row.providerId, row.modelId)] ??
              defaultModelAccessState,
            sort_order: idx,
          };
        })
        .filter((row): row is { provider_id: string; model_id: string; access_state: AccessState; sort_order: number } => row !== null);
      const model_defaults = (Object.entries(modelDefaults) as Array<[ModelProfile, string]>)
        .map(([profile, value]) => {
          const [providerId, ...modelParts] = value.split(":");
          const modelId = modelParts.join(":").trim();
          return providerId && modelId ? { profile, provider_id: providerId, model_id: modelId } : null;
        })
        .filter((row): row is { profile: ModelProfile; provider_id: string; model_id: string } => row !== null);
      const provider_capabilities = capabilityProviders.map((provider) => ({
        capability: provider.capability,
        provider_id: provider.providerId,
        access_state:
          capabilityAccess[capabilityAccessKey(provider.capability, provider.providerId)] ??
          defaultProviderCapabilityState,
      }));
      const res = await apiFetch(endpoint, auth, {
        method: "PUT",
        body: JSON.stringify({ model_access, model_defaults, provider_capabilities }),
      });
      const data = (await res.json().catch(() => ({}))) as ModelAccessPayload;
      if (!res.ok) {
        const detail = typeof data.detail === "string" ? data.detail : t("admin:modelAccessSaveFailed");
        setPolicyMsg({ ok: false, text: detail });
        return false;
      }
      setPolicyMsg({ ok: true, text: t("admin:modelAccessSaveOk") });
      return true;
    } catch (e) {
      setPolicyMsg({ ok: false, text: e instanceof Error ? e.message : t("admin:modelAccessSaveFailed") });
      return false;
    } finally {
      setPolicySaving(false);
    }
  }
  if (s.loading) {
    return <p className="text-sm text-ink-muted">{t("admin:loading")}</p>;
  }
  return (
    <>
          {showProviders ? (
          <section className="rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifLlmEndpointsTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifLlmEndpointsIntro")}</p>
            <div className="mt-wide rounded-card border border-sky-400/25 bg-sky-500/10 p-wide">
              <h3 className="text-sm font-medium text-sky-100">{t("admin:ifLlmActiveCatalogTitle")}</h3>
              <p className="mt-tight text-xs text-sky-100/75">{t("admin:ifLlmActiveCatalogIntro")}</p>
              <div className="mt-soft grid gap-soft xl:grid-cols-2">
                {accessProviderGroups.map((group) => (
                  <div key={group.id} className="rounded-tile border border-line bg-black/25 p-soft">
                    <div className="flex items-start justify-between gap-soft">
                      <div>
                        <h4 className="text-xs font-semibold text-ink-primary">{group.title}</h4>
                        <p className="mt-tight text-meta text-sky-100/70">{group.intro}</p>
                      </div>
                      <span className="rounded-tile bg-white/10 px-snug py-hair font-mono text-meta text-ink-secondary">
                        {group.providers.length}
                      </span>
                    </div>
                    {group.providers.length === 0 ? (
                      <p className="mt-soft text-xs text-amber-200">{group.empty}</p>
                    ) : (
                      <div className="mt-soft space-y-base">
                        {group.providers.map((provider) => {
                          const visibleModels = provider.models ?? [];
                          return (
                            <div key={capabilityAccessKey(provider.capability, provider.providerId)} className="rounded-tile border border-line bg-black/25 p-soft">
                              <div className="flex flex-wrap items-center gap-base">
                                <span className="text-xs font-semibold text-ink-primary">{provider.label}</span>
                                <span className="font-mono text-xs text-ink-muted">{provider.providerId}</span>
                                {provider.source ? (
                                  <span className="rounded-tile bg-white/10 px-snug py-hair text-meta uppercase tracking-wide text-ink-secondary">
                                    {provider.source}
                                  </span>
                                ) : null}
                                {provider.meta ? (
                                  <span className="text-meta text-ink-secondary">{provider.meta}</span>
                                ) : null}
                              </div>
                              {provider.baseUrl ? (
                                <p className="mt-tight break-all font-mono text-meta text-ink-muted">{provider.baseUrl}</p>
                              ) : null}
                              {visibleModels.length > 0 ? (
                                <div className="mt-base flex flex-wrap gap-tight">
                                  {visibleModels.map((model) => (
                                    <span
                                      key={model}
                                      className="rounded-tile border border-line bg-black/30 px-snug py-hair font-mono text-meta text-ink-primary"
                                    >
                                      {model}
                                    </span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
            {operatorEnvImportGroups.map((group) => (
              <div key={group.kind} className="mt-wide rounded-card border border-amber-400/25 bg-amber-500/10 p-wide">
                <div className="flex flex-col gap-soft sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-amber-100">
                      {t("admin:envProviderFoundTitle", { count: group.providers.length })}
                    </h3>
                    <p className="mt-tight text-xs text-amber-100/75">
                      {t("admin:envProviderFoundIntro", { prefix: group.envPrefix })}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={s.envOperatorImporting === group.kind}
                    className="rounded-tile bg-amber-500 px-soft py-snug text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50"
                    onClick={() => void s.importOperatorEnvProviders(group.kind)}
                  >
                    {s.envOperatorImporting === group.kind ? t("admin:envLlmImporting") : t("admin:envLlmImportButton")}
                  </button>
                </div>
                <div className="mt-soft space-y-base">
                  {group.providers.map((p) => (
                    <details key={p.provider_id} className="rounded-tile border border-line bg-black/25 p-soft">
                      <summary className="cursor-pointer text-xs text-amber-100">
                        <span className="font-mono">{p.provider_id}</span> · {p.label}
                        {p.already_in_db ? ` · ${t("admin:envLlmAlreadyInDb")}` : ""}
                      </summary>
                      <p className="mt-base break-all font-mono text-meta text-ink-muted">{p.base_url}</p>
                      <div className="mt-base grid gap-base text-meta text-ink-secondary sm:grid-cols-2">
                        <p>
                          {t("admin:envLlmModels")}: <span className="font-mono">{p.model_default || "—"}</span>
                        </p>
                        <p>
                          {t("admin:envLlmKey")}:{" "}
                          {p.api_key_configured
                            ? t("admin:envLlmKeyRedacted", { last4: p.api_key_last4 ?? t("admin:envLlmKeyLast4Unknown") })
                            : t("admin:envLlmKeyEmpty")}
                        </p>
                        <p>
                          {t("admin:envLlmHeader")}: <span className="font-mono">{p.api_header_name}</span>
                        </p>
                      </div>
                      <details className="mt-base">
                        <summary className="cursor-pointer text-meta text-amber-100/80">
                          {t("admin:envLlmCleanupChecklist")}
                        </summary>
                        <ul className="mt-tight grid gap-tight sm:grid-cols-2">
                          {p.cleanup_keys.map((key) => (
                            <li key={key} className="font-mono text-meta text-amber-100/70">
                              {key}
                            </li>
                          ))}
                        </ul>
                      </details>
                    </details>
                  ))}
                </div>
                {s.envOperatorCleanupNotes[group.kind] ? (
                  <p className="mt-soft text-xs text-amber-100/75">{s.envOperatorCleanupNotes[group.kind]}</p>
                ) : null}
              </div>
            ))}
            {operatorDbEndpointGroups.length > 0 ? (
              <div className="mt-broad grid gap-wide xl:grid-cols-2">
                {operatorDbEndpointGroups.map((group) => (
                  <div key={group.kind} className="rounded-card border border-line bg-black/15 p-wide">
                    <div className="flex items-start justify-between gap-soft">
                      <div>
                        <h4 className="text-sm font-medium text-ink-primary">{group.title}</h4>
                        <p className="mt-tight text-xs text-ink-muted">{group.intro}</p>
                      </div>
                      <span className="rounded-tile bg-white/10 px-snug py-hair font-mono text-meta text-ink-secondary">
                        {group.endpoints.length}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="mt-soft rounded-tile border border-sky-500/40 bg-sky-500/10 px-soft py-snug text-xs text-sky-200 hover:bg-sky-500/20"
                      onClick={() => addOperatorEndpoint(group.kind)}
                    >
                      {t("admin:ifMemAddEndpoint")}
                    </button>
                    <div className="mt-soft space-y-soft">
                      {group.endpoints.length === 0 ? (
                        <p className="rounded-tile border border-amber-400/20 bg-amber-500/10 px-soft py-base text-xs text-amber-100">
                          {adminText(group.metadata.empty_i18n_key)}
                        </p>
                      ) : null}
                      {group.endpoints.map((endpoint, endpointIdx) => {
                        const providerModelKey = s.operatorProviderModelKey(
                          group.kind,
                          operatorEndpointProviderId(endpoint)
                        );
                        const models = endpoint.models.length > 0 ? endpoint.models : (s.operatorProviderModelOptions[providerModelKey] ?? []);
                        return (
                        <div
                          key={`${group.kind}-${endpoint.id ?? endpointIdx}`}
                          className="rounded-tile border border-line bg-black/25 p-soft"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-base">
                            <div className="flex flex-wrap items-center gap-base">
                            <span className="text-xs font-semibold text-ink-primary">
                              {endpoint.label || endpoint.baseUrl || t("admin:ifMemEndpointN", { n: endpointIdx + 1 })}
                            </span>
                            {endpoint.id != null ? (
                              <span className="font-mono text-meta text-ink-muted">
                                {t("admin:dbEndpointBadge", { id: endpoint.id })}
                              </span>
                            ) : null}
                            <span className="rounded-tile bg-white/10 px-snug py-hair text-meta uppercase tracking-wide text-ink-secondary">
                              db
                            </span>
                            {endpoint.enabled ? null : (
                              <span className="rounded-tile bg-amber-500/15 px-snug py-hair text-meta text-amber-100">
                                {t("admin:off")}
                              </span>
                            )}
                            </div>
                            <Button
                              type="button"
                              variant="danger"
                              size="sm"
                              onClick={() => removeOperatorEndpoint(group.kind, endpointIdx)}
                            >
                              {t("admin:ifLlmRemove")}
                            </Button>
                          </div>
                          <label className="mt-soft flex cursor-pointer items-center gap-base text-xs text-ink-primary">
                            <input
                              type="checkbox"
                              className="rounded-tile border-line"
                              checked={endpoint.enabled}
                              onChange={(e) => updateOperatorEndpoint(group.kind, endpointIdx, { enabled: e.target.checked })}
                            />
                            {t("admin:on")}
                          </label>
                          <label className="mt-base block text-xs text-ink-muted" htmlFor={`provider-label-${group.kind}-${endpointIdx}`}>
                            {t("admin:ifLlmLabelOptional")}
                          </label>
                          <input
                            id={`provider-label-${group.kind}-${endpointIdx}`}
                            className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
                            value={endpoint.label}
                            onChange={(e) => updateOperatorEndpoint(group.kind, endpointIdx, { label: e.target.value })}
                            placeholder={group.title}
                          />
                          <label className="mt-soft block text-xs text-ink-muted" htmlFor={`provider-url-${group.kind}-${endpointIdx}`}>
                            {t("admin:ifMemBaseUrlLabel")}
                          </label>
                          <input
                            id={`provider-url-${group.kind}-${endpointIdx}`}
                            className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                            value={endpoint.baseUrl}
                            onChange={(e) => updateOperatorEndpoint(group.kind, endpointIdx, { baseUrl: e.target.value })}
                            placeholder={t("admin:ifLlmBaseUrlPlaceholder")}
                            autoComplete="off"
                          />
                          <div className="mt-soft grid gap-soft sm:grid-cols-2">
                            <div>
                              <label className="block text-xs text-ink-muted" htmlFor={`provider-header-${group.kind}-${endpointIdx}`}>
                                {t("admin:envLlmHeader")}
                              </label>
                              <input
                                id={`provider-header-${group.kind}-${endpointIdx}`}
                                className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                                value={endpoint.apiHeaderName}
                                onChange={(e) => updateOperatorEndpoint(group.kind, endpointIdx, { apiHeaderName: e.target.value })}
                                placeholder={endpoint.apiHeaderName || "Authorization"}
                              />
                            </div>
                            <div>
                              <label className="block text-xs text-ink-muted" htmlFor={`provider-model-${group.kind}-${endpointIdx}`}>
                                {adminText(group.metadata.model_label_i18n_key, "Model")}
                              </label>
                              <ProviderModelSelect
                                id={`provider-model-${group.kind}-${endpointIdx}`}
                                value={endpoint.modelDefault}
                                models={models}
                                placeholder={adminText(group.metadata.model_placeholder_i18n_key, t("admin:ifLlmSelectProviderModel"))}
                                onChange={(value) => updateOperatorEndpoint(group.kind, endpointIdx, { modelDefault: value })}
                              />
                            </div>
                          </div>
                          <label className="mt-soft block text-xs text-ink-muted" htmlFor={`provider-parallel-${group.kind}-${endpointIdx}`}>
                            {t("admin:ifLlmMaxParallelLabel")}
                          </label>
                          <input
                            id={`provider-parallel-${group.kind}-${endpointIdx}`}
                            type="number"
                            min={1}
                            max={64}
                            step={1}
                            className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                            value={endpoint.maxParallel}
                            onChange={(e) =>
                              updateOperatorEndpoint(group.kind, endpointIdx, {
                                maxParallel: Math.max(1, Math.min(64, Math.floor(Number(e.target.value) || 1))),
                              })
                            }
                          />
                          <p className="mt-tight text-xs text-ink-muted">{t("admin:ifLlmMaxParallelHint")}</p>
                          <p className="mt-soft text-xs text-ink-muted">
                            {t("admin:envLlmKey")}:{" "}
                            {endpoint.apiKeyConfigured
                              ? t("admin:envLlmKeyRedacted", {
                                  last4: endpoint.apiKeyLast4 ?? t("admin:envLlmKeyLast4Unknown"),
                                })
                              : t("admin:envLlmKeyEmpty")}
                          </p>
                          <label className="mt-base block text-xs text-ink-muted" htmlFor={`provider-key-${group.kind}-${endpointIdx}`}>
                            {t("admin:ifMemApiKeyLabel")}
                          </label>
                          <input
                            id={`provider-key-${group.kind}-${endpointIdx}`}
                            type="password"
                            autoComplete="off"
                            className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                            value={endpoint.apiKey ?? ""}
                            onChange={(e) => updateOperatorEndpoint(group.kind, endpointIdx, { apiKey: e.target.value })}
                            placeholder={endpoint.apiKeyConfigured ? t("admin:tokenReplacePlaceholder") : t("admin:ifMemPasteKey")}
                          />
                        </div>
                      );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
          ) : null}

          {showPolicies ? (
          <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifLlmChatVisibilityTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifLlmChatVisibilityIntro")}</p>
            <div className="mt-wide rounded-card border border-line bg-black/15 p-soft">
              <div className="grid gap-soft lg:grid-cols-3">
                <div>
                  <label className="block text-xs text-ink-muted" htmlFor="model-access-scope">
                    {t("admin:modelAccessScope")}
                  </label>
                  <select
                    id="model-access-scope"
                    className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
                    value={accessScope}
                    onChange={(e) => setAccessScope(e.target.value as AccessScope)}
                  >
                    <option value="global">{t("admin:modelAccessScopeGlobal")}</option>
                    {showTenantScope ? (
                      <option value="tenant">{t("admin:modelAccessScopeTenant")}</option>
                    ) : null}
                    <option value="user">{t("admin:modelAccessScopeUser")}</option>
                  </select>
                </div>
                {showTenantScope && accessScope === "tenant" ? (
                  <div>
                    <label className="block text-xs text-ink-muted" htmlFor="model-access-tenant">
                      {t("admin:modelAccessTenant")}
                    </label>
                    <select
                      id="model-access-tenant"
                      className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
                      value={accessTenantId}
                      onChange={(e) => setAccessTenantId(e.target.value)}
                    >
                      {tenants.map((row) => (
                        <option key={row.id} value={row.id}>
                          {tenantLabel(row, t("admin:modelAccessTenant"))}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : null}
                {accessScope === "user" ? (
                  <div>
                    <label className="block text-xs text-ink-muted" htmlFor="model-access-user">
                      {t("admin:modelAccessUser")}
                    </label>
                    <select
                      id="model-access-user"
                      className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
                      value={accessUserId}
                      onChange={(e) => setAccessUserId(e.target.value)}
                    >
                      {users.map((row) => (
                        <option key={row.id} value={row.id}>
                          {userLabel(row)}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : null}
              </div>
              <div className="mt-wide grid gap-soft lg:grid-cols-4">
                {catalogRuntimeModelDefaults.map(({ metadata, profile }) => (
                  <div key={metadata.profile}>
                    <label className="block text-xs text-ink-muted" htmlFor={`model-default-${profile}`}>
                      {adminText(metadata.title_i18n_key, profile)}
                    </label>
                    <select
                      id={`model-default-${profile}`}
                      className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-xs text-ink-primary"
                      value={modelDefaults[profile]}
                      onChange={(e) => setModelDefaults((prev) => ({ ...prev, [profile]: e.target.value }))}
                    >
                      <option value="">{t("admin:modelAccessNoDefault")}</option>
                      {modelOptions.map((row) => (
                        <option key={`${profile}:${row.value}`} value={row.value}>
                          {row.providerId}: {row.modelId}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              {nonChatRuntimeModelDefaults.length > 0 ? (
                <div className="mt-wide grid gap-soft lg:grid-cols-4">
                  {nonChatRuntimeModelDefaults.map(({ metadata, profile, models }) => (
                    <div key={metadata.kind}>
                      <label className="block text-xs text-ink-muted" htmlFor={`runtime-default-${metadata.kind}`}>
                        {adminText(metadata.model_label_i18n_key, metadata.kind)}
                      </label>
                      <select
                        id={`runtime-default-${metadata.kind}`}
                        className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-xs text-ink-primary"
                        value={modelDefaults[profile] ?? ""}
                        onChange={(e) => setModelDefaults((prev) => ({ ...prev, [profile]: e.target.value }))}
                      >
                        <option value="">{t("admin:modelAccessNoDefault")}</option>
                        {models.map((row) => (
                          <option key={`${metadata.kind}:${row.value}`} value={row.value}>
                            {row.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="mt-wide flex flex-wrap items-center gap-soft">
                <button
                  type="button"
                  className="rounded-tile bg-sky-500 px-soft py-snug text-sm font-medium text-ink-on-fill hover:bg-sky-400 disabled:opacity-50"
                  disabled={policySaving || policyLoading}
                  onClick={() => void saveModelAccessPolicy()}
                >
                  {policySaving ? t("admin:modelAccessSaving") : t("admin:modelAccessSave")}
                </button>
                {policyMsg ? (
                  <span className={`text-xs ${policyMsg.ok ? "text-emerald-300" : "text-amber-300"}`}>
                    {policyMsg.text}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="mt-wide grid gap-soft xl:grid-cols-2">
              {accessProviderGroups.map((group) => (
                <div key={group.id} className="rounded-card border border-line bg-black/15 p-soft">
                  <div className="flex items-start justify-between gap-soft">
                    <div>
                      <h3 className="text-sm font-medium text-ink-primary">{group.title}</h3>
                      <p className="mt-tight text-xs text-ink-muted">{group.intro}</p>
                    </div>
                    <span className="rounded-tile bg-white/10 px-snug py-hair font-mono text-meta text-ink-secondary">
                      {group.providers.length}
                    </span>
                  </div>
                  {group.providers.length === 0 ? (
                    <p className="mt-soft rounded-tile border border-amber-400/20 bg-amber-500/10 px-soft py-base text-xs text-amber-100">
                      {group.empty}
                    </p>
                  ) : (
                    <div className="mt-soft space-y-base">
                      {group.providers.map((provider) => {
                        const key = capabilityAccessKey(provider.capability, provider.providerId);
                        const state = capabilityAccess[key] ?? defaultProviderCapabilityState;
                        return (
                          <div
                            key={key}
                            className="flex items-center gap-soft rounded-card border border-line-subtle bg-black/20 px-soft py-base"
                          >
                            <span className="min-w-0 flex-1">
                              <span className="flex flex-wrap items-center gap-base text-xs font-medium text-ink-primary">
                                <span>{provider.label}</span>
                                <span className="font-mono text-meta text-ink-muted">{provider.providerId}</span>
                                {provider.source ? (
                                  <span className="rounded-tile bg-white/10 px-snug py-hair text-meta uppercase tracking-wide text-ink-secondary">
                                    {provider.source}
                                  </span>
                                ) : null}
                              </span>
                              {provider.baseUrl ? (
                                <span className="mt-tight block truncate font-mono text-meta text-ink-muted">
                                  {provider.baseUrl}
                                </span>
                              ) : null}
                              {provider.meta ? (
                                <span className="mt-tight block truncate text-meta text-ink-secondary">{provider.meta}</span>
                              ) : null}
                            </span>
                            <AccessStateControl
                              value={state}
                              labels={{
                                inherit: t("admin:modelAccessInherit"),
                                allow: t("admin:modelAccessAllow"),
                                deny: t("admin:modelAccessDeny"),
                              }}
                              onChange={(next) =>
                                setCapabilityAccess((prev) => ({
                                  ...prev,
                                  [key]: next,
                                }))
                              }
                            />
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {modelAccessProviderGroups.length === 0 ? (
              <p className="mt-wide text-xs text-amber-300/90">{t("admin:ifLlmChatVisibilityEmpty")}</p>
            ) : (
              <div className="mt-wide max-h-96 space-y-soft overflow-auto rounded-card border border-line bg-black/15 p-base">
                {modelAccessProviderGroups.map((provider) => {
                  return (
                    <div key={provider.providerId} className="rounded-card border border-line bg-black/20 p-soft">
                      <div className="mb-base flex flex-wrap items-center gap-base">
                        <span className="text-xs font-semibold text-ink-primary">{provider.label}</span>
                        <span className="font-mono text-meta text-ink-muted">{provider.providerId}</span>
                        <span className="rounded-tile bg-white/10 px-snug py-hair text-meta uppercase tracking-wide text-ink-secondary">
                          {provider.source}
                        </span>
                        {provider.endpointId != null ? (
                          <span className="font-mono text-meta text-ink-muted">
                            {t("admin:dbEndpointBadge", { id: provider.endpointId })}
                          </span>
                        ) : null}
                      </div>
                      <div className="space-y-base">
                        {provider.rows.map((row) => {
                          const providerId = (row.owned_by ?? provider.providerId).trim().toLowerCase();
                          const modelId = row.id.trim();
                          const key = s.modelPrefKey(providerId, modelId);
                          const accessKey = modelAccessKey(providerId, modelId);
                          const accessState = modelAccess[accessKey] ?? defaultModelAccessState;
                          const visible = accessState !== "deny";
                          const profileBadges = provider.profileSource
                            ? profileBadgesForModel(provider.profileSource, modelId)
                            : [];
                          return (
                            <div
                              key={key}
                              className="flex items-start gap-soft rounded-card border border-line-subtle bg-black/20 px-soft py-base"
                            >
                              <span className="min-w-0 flex-1">
                                <span className="block truncate font-mono text-xs text-ink-primary">{modelId}</span>
                                <span className="block truncate text-meta text-ink-muted">{provider.label}</span>
                              </span>
                              <AccessStateControl
                                value={accessState}
                                labels={{
                                  inherit: t("admin:modelAccessInherit"),
                                  allow: t("admin:modelAccessAllow"),
                                  deny: t("admin:modelAccessDeny"),
                                }}
                                onChange={(next) =>
                                  setModelAccess((prev) => ({
                                    ...prev,
                                    [accessKey]: next,
                                  }))
                                }
                              />
 <span className="flex shrink-0 flex-wrap justify-end gap-tight pt-hair">
                                {profileBadges.map((badge) => (
                                  <span
                                    key={badge}
                                    className="inline-flex rounded-pill border border-sky-400/30 bg-sky-500/10 px-snug py-hair text-meta font-medium text-sky-100"
                                  >
                                    {badge}
                                  </span>
                                ))}
                                {modelCapabilityBadges(row).map((badge) => (
                                  <span
                                    key={badge.key}
                                    className="inline-flex rounded-pill border border-line bg-white/5 px-snug py-hair text-meta font-medium text-ink-primary"
                                  >
                                    {badge.label}
                                  </span>
                                ))}
                                <span
                                  className={`inline-flex rounded-pill border px-snug py-hair text-meta font-medium ${
                                    visible
                                      ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
                                      : "border-danger/30 bg-danger-subtle text-badge-danger"
                                  }`}
                                >
                                  {t(`admin:modelAccessState_${accessState}`)}
                                </span>
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <p className="mt-base text-xs text-ink-muted">{t("admin:modelAccessSaveHint")}</p>
          </section>
          ) : null}

          {showRouting ? (
          <>
          <section className="mt-broad rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifLlmSmartRoutingTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifLlmSmartRoutingIntro")}</p>
            <label className="mt-wide flex cursor-pointer items-center gap-base text-sm text-ink-primary">
              <input
                type="checkbox"
                className="rounded-tile border-line"
                checked={s.llmSmartRouting}
                onChange={(e) => s.setLlmSmartRouting(e.target.checked)}
              />
              {t("admin:ifLlmSmartRoutingEnable")}
            </label>
            <label className="mt-wide block text-xs text-ink-muted" htmlFor="llm-router-model">
              {t("admin:ifLlmRouterModel")}
            </label>
            <select
              id="llm-router-model"
              className="mt-tight w-full max-w-controlWide rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary disabled:opacity-50"
              value={
                s.llmRouterModelProvider && s.llmRouterModel
                  ? `${s.llmRouterModelProvider}:${s.llmRouterModel}`
                  : ""
              }
              disabled={effectiveCatalogRows.length === 0}
              onChange={(e) => {
                const [provider, ...modelParts] = e.target.value.split(":");
                s.setLlmRouterModelProvider(provider || "");
                s.setLlmRouterModel(modelParts.join(":") || "");
              }}
            >
              <option value="">{t("admin:ifLlmSelectProviderModel")}</option>
              {effectiveCatalogRows.map((row) => {
                const providerId = (row.owned_by ?? "").trim().toLowerCase();
                const modelId = row.id.trim();
                if (!providerId || !modelId) return null;
                return (
                  <option key={`${providerId}:${modelId}`} value={`${providerId}:${modelId}`}>
                    {providerId}: {modelId}
                  </option>
                );
              })}
            </select>
            <div className="mt-wide grid max-w-measure gap-soft sm:grid-cols-2">
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-router-conf">
                  {t("admin:ifLlmRouterConfMin")}
                </label>
                <input
                  id="llm-router-conf"
                  type="number"
                  step="0.05"
                  min={0}
                  max={1}
                  className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmRouterConfMin}
                  onChange={(e) => s.setLlmRouterConfMin(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-router-to">
                  {t("admin:ifLlmRouterTimeout")}
                </label>
                <input
                  id="llm-router-to"
                  type="number"
                  min={1}
                  max={120}
                  step="1"
                  className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmRouterTimeoutSec}
                  onChange={(e) => s.setLlmRouterTimeoutSec(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-route-long">
                  {t("admin:ifLlmRouteLongChars")}
                </label>
                <input
                  id="llm-route-long"
                  type="number"
                  min={100}
                  max={500000}
                  className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmRouteLongChars}
                  onChange={(e) => s.setLlmRouteLongChars(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-route-short">
                  {t("admin:ifLlmRouteShortChars")}
                </label>
                <input
                  id="llm-route-short"
                  type="number"
                  min={1}
                  max={50000}
                  className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmRouteShortChars}
                  onChange={(e) => s.setLlmRouteShortChars(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-route-fences">
                  {t("admin:ifLlmRouteFences")}
                </label>
                <input
                  id="llm-route-fences"
                  type="number"
                  min={1}
                  max={100}
                  className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmRouteManyFences}
                  onChange={(e) => s.setLlmRouteManyFences(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-route-msgs">
                  {t("admin:ifLlmRouteManyMsgs")}
                </label>
                <input
                  id="llm-route-msgs"
                  type="number"
                  min={1}
                  max={500}
                  className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmRouteManyMsgs}
                  onChange={(e) => s.setLlmRouteManyMsgs(e.target.value)}
                />
              </div>
            </div>
          </section>

          <section className="rounded-sheet border border-line bg-card p-roomy">
            <h2 className="text-sm font-medium text-ink-primary">{t("admin:ifLlmQueueTitle")}</h2>
            <p className="mt-base text-xs text-ink-muted">{t("admin:ifLlmQueueIntro")}</p>
            <div className="mt-wide grid gap-wide sm:grid-cols-2">
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-queue-policy">
                  {t("admin:ifLlmQueuePolicyLabel")}
                </label>
                <select
                  id="llm-queue-policy"
                  className="mt-tight w-full rounded-tile border border-line bg-field px-soft py-base text-sm text-ink-primary"
                  value={s.llmQueuePolicy}
                  onChange={(e) =>
                    s.setLlmQueuePolicy(
                      e.target.value as "fifo" | "priority" | "round_robin"
                    )
                  }
                >
                  <option value="priority">{t("admin:ifLlmQueuePolicyPriority")}</option>
                  <option value="fifo">{t("admin:ifLlmQueuePolicyFifo")}</option>
                  <option value="round_robin">{t("admin:ifLlmQueuePolicyRoundRobin")}</option>
                </select>
                <p className="mt-tight text-xs text-ink-muted">{t("admin:ifLlmQueuePolicyHint")}</p>
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-queue-user-prio">
                  {t("admin:ifLlmQueueUserPriority")}
                </label>
                <input
                  id="llm-queue-user-prio"
                  type="number"
                  min={0}
                  max={1000}
                  className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmQueueUserPriority}
                  onChange={(e) => s.setLlmQueueUserPriority(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-queue-bench-prio">
                  {t("admin:ifLlmQueueBenchmarkPriority")}
                </label>
                <input
                  id="llm-queue-bench-prio"
                  type="number"
                  min={0}
                  max={1000}
                  className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmQueueBenchmarkPriority}
                  onChange={(e) => s.setLlmQueueBenchmarkPriority(e.target.value)}
                />
                <p className="mt-tight text-xs text-ink-muted">{t("admin:ifLlmQueueBenchmarkHint")}</p>
              </div>
              <div>
                <label className="block text-xs text-ink-muted" htmlFor="llm-queue-sched-prio">
                  {t("admin:ifLlmQueueSchedulerPriority")}
                </label>
                <input
                  id="llm-queue-sched-prio"
                  type="number"
                  min={0}
                  max={1000}
                  className="mt-tight w-full max-w-control rounded-tile border border-line bg-field px-soft py-base font-mono text-sm text-ink-primary"
                  value={s.llmQueueSchedulerPriority}
                  onChange={(e) => s.setLlmQueueSchedulerPriority(e.target.value)}
                />
              </div>
            </div>
          </section>
          </>
          ) : null}
    </>
  );
}
