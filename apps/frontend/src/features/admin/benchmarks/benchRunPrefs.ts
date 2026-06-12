/** Persist admin benchmark run form (localStorage, per browser). */

const STORAGE_KEY = "agentlayer.admin.benchRunPrefs";
const PREFS_VERSION = 2;

export type BenchRunPrefs = {
  v: typeof PREFS_VERSION;
  suite: string;
  runAsUserId: string;
  friendUserId: string;
  promptLocale: string;
  scenarioTimeoutSec: string;
  maxToolRoundsOverride: string;
  retainWorkspaces: boolean;
  selectedProviderIds: string[];
  modelByProviderId: Record<string, string>;
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
    scenarioTimeoutSec: "",
    maxToolRoundsOverride: "",
    retainWorkspaces: false,
    selectedProviderIds: [],
    modelByProviderId: {},
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

export function loadBenchRunPrefs(): BenchRunPrefsInput | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<BenchRunPrefs>;
    if (parsed.v !== PREFS_VERSION) return null;
    const base = emptyPrefs();
    return {
      suite: typeof parsed.suite === "string" && parsed.suite.trim() ? parsed.suite.trim() : base.suite,
      runAsUserId: typeof parsed.runAsUserId === "string" ? parsed.runAsUserId : "",
      friendUserId: typeof parsed.friendUserId === "string" ? parsed.friendUserId : "",
      promptLocale:
        typeof parsed.promptLocale === "string" && parsed.promptLocale.trim()
          ? parsed.promptLocale.trim().toLowerCase()
          : base.promptLocale,
      scenarioTimeoutSec:
        typeof parsed.scenarioTimeoutSec === "string" ? parsed.scenarioTimeoutSec : "",
      maxToolRoundsOverride:
        typeof parsed.maxToolRoundsOverride === "string" ? parsed.maxToolRoundsOverride : "",
      retainWorkspaces: parsed.retainWorkspaces === true,
      selectedProviderIds: Array.isArray(parsed.selectedProviderIds)
        ? parsed.selectedProviderIds.map((x) => String(x).trim()).filter(Boolean)
        : [],
      modelByProviderId:
        parsed.modelByProviderId && typeof parsed.modelByProviderId === "object"
          ? Object.fromEntries(
              Object.entries(parsed.modelByProviderId as Record<string, unknown>)
                .map(([k, v]) => [k, String(v ?? "").trim()] as const)
                .filter(([k, v]) => k && v)
            )
          : {},
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
    const payload: BenchRunPrefs = { v: PREFS_VERSION, ...input };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}
