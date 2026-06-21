/** Persist admin benchmark run form (localStorage, per browser). */

import { normalizeProviderModels } from "./benchProfileSelection";

const STORAGE_KEY = "agentlayer.admin.benchRunPrefs";
const PREFS_VERSION = 10;

export type BenchRunPrefs = {
  v: typeof PREFS_VERSION;
  suite: string;
  runAsUserId: string;
  friendUserId: string;
  promptLocale: string;
  promptVariant: string;
  cohortLabel: string;
  scenarioTimeoutSec: string;
  maxToolRoundsOverride: string;
  scenarioFailureRetries: string;
  retainWorkspaces: boolean;
  selectedProviderIds: string[];
  modelsByProviderId: Record<string, string[]>;
  scenariosBySuite: Record<string, string[]>;
  extraFixturesBySuite: Record<string, string[]>;
};

export type BenchRunPrefsInput = Omit<BenchRunPrefs, "v">;

function emptyPrefs(): BenchRunPrefsInput {
  return {
    suite: "smoke",
    runAsUserId: "",
    friendUserId: "",
    promptLocale: "en",
    promptVariant: "canonical",
    cohortLabel: "",
    scenarioTimeoutSec: "",
    maxToolRoundsOverride: "",
    scenarioFailureRetries: "0",
    retainWorkspaces: false,
    selectedProviderIds: [],
    modelsByProviderId: {},
    scenariosBySuite: {},
    extraFixturesBySuite: {},
  };
}

function normalizeRecord(raw: unknown): Record<string, string[]> {
  if (!raw || typeof raw !== "object") return {};
  const out: Record<string, string[]> = {};
  for (const [key, val] of Object.entries(raw as Record<string, unknown>)) {
    if (!key.trim()) continue;
    if (!Array.isArray(val)) continue;
    const ids = val.map((x) => String(x).trim()).filter(Boolean);
    if (ids.length) out[key.trim()] = ids;
  }
  return out;
}

function migrateModelsByProvider(parsed: Record<string, unknown>): Record<string, string[]> {
  if (parsed.modelsByProviderId && typeof parsed.modelsByProviderId === "object") {
    return normalizeRecord(parsed.modelsByProviderId);
  }
  if (parsed.modelByProviderId && typeof parsed.modelByProviderId === "object") {
    const out: Record<string, string[]> = {};
    for (const [key, val] of Object.entries(parsed.modelByProviderId as Record<string, unknown>)) {
      const id = key.trim();
      const model = String(val ?? "").trim();
      if (id && model) out[id] = [model];
    }
    return out;
  }
  return {};
}

export function loadBenchRunPrefs(): BenchRunPrefsInput | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<BenchRunPrefs> & {
      modelByProviderId?: Record<string, string>;
      sessionId?: string;
    };
    if (
      parsed.v !== PREFS_VERSION &&
      parsed.v !== 9 &&
      parsed.v !== 8 &&
      parsed.v !== 7 &&
      parsed.v !== 6 &&
      parsed.v !== 5 &&
      parsed.v !== 4 &&
      parsed.v !== 3
    ) {
      return null;
    }
    const base = emptyPrefs();
    return {
      suite: typeof parsed.suite === "string" && parsed.suite.trim() ? parsed.suite.trim() : base.suite,
      runAsUserId: typeof parsed.runAsUserId === "string" ? parsed.runAsUserId : "",
      friendUserId: typeof parsed.friendUserId === "string" ? parsed.friendUserId : "",
      promptLocale:
        typeof parsed.promptLocale === "string" && parsed.promptLocale.trim()
          ? parsed.promptLocale.trim().toLowerCase()
          : base.promptLocale,
      promptVariant:
        typeof parsed.promptVariant === "string" && parsed.promptVariant.trim()
          ? parsed.promptVariant.trim().toLowerCase()
          : base.promptVariant,
      cohortLabel: typeof parsed.cohortLabel === "string" ? parsed.cohortLabel : "",
      scenarioTimeoutSec:
        typeof parsed.scenarioTimeoutSec === "string" ? parsed.scenarioTimeoutSec : "",
      maxToolRoundsOverride:
        typeof parsed.maxToolRoundsOverride === "string" ? parsed.maxToolRoundsOverride : "",
      scenarioFailureRetries:
        typeof parsed.scenarioFailureRetries === "string" ? parsed.scenarioFailureRetries : "0",
      retainWorkspaces: parsed.retainWorkspaces === true,
      selectedProviderIds: Array.isArray(parsed.selectedProviderIds)
        ? parsed.selectedProviderIds.map((x) => String(x).trim()).filter(Boolean)
        : [],
      modelsByProviderId: migrateModelsByProvider(parsed as Record<string, unknown>),
      scenariosBySuite: normalizeRecord(parsed.scenariosBySuite),
      extraFixturesBySuite: normalizeRecord(parsed.extraFixturesBySuite),
    };
  } catch {
    return null;
  }
}

export function saveBenchRunPrefs(input: BenchRunPrefsInput): void {
  if (typeof localStorage === "undefined") return;
  try {
    const modelsByProviderId: Record<string, string[]> = {};
    for (const [key, models] of Object.entries(input.modelsByProviderId)) {
      const normalized = normalizeProviderModels(models);
      if (normalized.length) modelsByProviderId[key] = normalized;
    }
    const payload: BenchRunPrefs = {
      v: PREFS_VERSION,
      ...input,
      modelsByProviderId,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}
