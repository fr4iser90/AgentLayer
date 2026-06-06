import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import i18n from "../i18n/config";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "../lib/api";
import { DashboardEmbeddedChat } from "../features/dashboard/DashboardEmbeddedChat";
import {
  DashboardOnboardingBanner,
  isOnboardingDismissed,
} from "../features/dashboard/DashboardOnboardingBanner";
import { DashboardGridCanvas } from "../features/dashboard/DashboardGridCanvas";
import { DashboardSettingsDrawer } from "../features/dashboard/DashboardSettingsDrawer";
import { DashboardHubNavigator } from "../features/dashboard/DashboardHubNavigator";
import { DashboardOverviewPanel } from "../features/dashboard/DashboardOverviewPanel";
import { ProjectsImportModal } from "../features/dashboard/ProjectsImportModal";
import { CollapsibleSidebarShell } from "../layout/CollapsibleSidebarShell";
import { useNotificationContext } from "../features/notifications/NotificationProvider";
import {
  DEFAULT_HUBS,
  groupDashboardsByHub,
  hubForSelectedId,
  type DashboardHubId,
} from "../features/dashboard/dashboardHubNav";
import type {
  UiLayout,
  DashboardBlockGrantRow,
  DashboardDataAgentlayer,
  DashboardDetail,
  DashboardMemberRow,
  DashboardPublicShareRow,
  DashboardSummary,
} from "../features/dashboard/types";

function asUiLayout(raw: unknown): UiLayout | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as { version?: number; blocks?: unknown };
  if (!Array.isArray(o.blocks)) return null;
  return { version: Number(o.version) || 1, blocks: o.blocks as UiLayout["blocks"] };
}

type KindCatalogRow = {
  kind: string;
  label: string;
  description: string;
  has_template: boolean;
  has_schema: boolean;
};

function humanizeKindId(kind: string): string {
  const k = (kind || "").trim().toLowerCase();
  if (!k) return i18n.t("dashboard:kindDashboardDefault");
  return k.replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function parseKindCatalog(raw: unknown): KindCatalogRow[] {
  if (!Array.isArray(raw)) return [];
  const out: KindCatalogRow[] = [];
  for (const x of raw) {
    if (!x || typeof x !== "object") continue;
    const o = x as Record<string, unknown>;
    const kind = typeof o.kind === "string" ? o.kind.trim().toLowerCase() : "";
    if (!kind) continue;
    const label =
      typeof o.label === "string" && o.label.trim() ? o.label.trim() : humanizeKindId(kind);
    const description =
      typeof o.description === "string" && o.description.trim() ? o.description.trim() : "";
    out.push({
      kind,
      label,
      description,
      has_template: o.has_template === true,
      has_schema: o.has_schema === true,
    });
  }
  out.sort((a, b) => a.kind.localeCompare(b.kind));
  return out;
}

function labelForKind(kind: string, catalog: KindCatalogRow[]): string {
  const k = (kind || "").trim().toLowerCase();
  const row = catalog.find((r) => r.kind === k);
  if (row) return row.label;
  return humanizeKindId(kind);
}

function subtitleForDashboardKind(kind: string, catalog: KindCatalogRow[]): string {
  const row = catalog.find((r) => r.kind === (kind || "").trim().toLowerCase());
  if (row?.label) return row.label;
  return humanizeKindId(kind);
}

function normalizeKindList(raw: unknown): string[] | null {
  if (raw === null) return null;
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  for (const x of raw) {
    if (typeof x !== "string") continue;
    const k = x.trim().toLowerCase();
    if (k) out.push(k);
  }
  return out;
}

function relativeActivityEn(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "updated";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

type HubPanel = "home" | "catalog" | "overview";

export function DashboardPage() {
  const { t } = useTranslation(["dashboard", "admin"]);
  const auth = useAuth();
  const [searchParams] = useSearchParams();
  const { dashboardUnreadCount, blockUnreadIds, markDashboardSeen, refreshSummary } =
    useNotificationContext();
  const highlightBlockId = searchParams.get("block")?.trim() || null;
  const [schemaInstalled, setSchemaInstalled] = useState<boolean | null>(null);
  const [installBusy, setInstallBusy] = useState(false);
  const [installModalRow, setInstallModalRow] = useState<KindCatalogRow | null>(null);
  const [kindCatalog, setKindCatalog] = useState<KindCatalogRow[]>([]);
  const [installedTemplateKinds, setInstalledTemplateKinds] = useState<string[] | null>(null);
  const [list, setList] = useState<DashboardSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hubPanel, setHubPanel] = useState<HubPanel>("home");
  const [actionsSidebarOpen, setActionsSidebarOpen] = useState(false);
  const [newWsModalOpen, setNewWsModalOpen] = useState(false);
  const [projectsImportOpen, setProjectsImportOpen] = useState(false);
  const [onboardingHidden, setOnboardingHidden] = useState(false);
  const [chatComposeDraft, setChatComposeDraft] = useState("");
  const [chatComposeDraftSeed, setChatComposeDraftSeed] = useState(0);
  const [catalogQuery, setCatalogQuery] = useState("");
  const [detail, setDetail] = useState<DashboardDetail | null>(null);
  const [data, setData] = useState<Record<string, unknown>>({});
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [layoutEditMode, setLayoutEditMode] = useState(false);
  const [layoutDraft, setLayoutDraft] = useState<UiLayout>({ version: 1, blocks: [] });
  const [members, setMembers] = useState<DashboardMemberRow[]>([]);
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<"viewer" | "editor" | "co_owner">("viewer");
  const [membersBusy, setMembersBusy] = useState(false);
  const [membersErr, setMembersErr] = useState<string | null>(null);
  const [blockGrants, setBlockGrants] = useState<DashboardBlockGrantRow[]>([]);
  const [blockShareEmail, setBlockShareEmail] = useState("");
  const [blockSharePermission, setBlockSharePermission] = useState<"view" | "edit">("view");
  const [blockSharePick, setBlockSharePick] = useState<Record<string, boolean>>({});
  const [blockSharesBusy, setBlockSharesBusy] = useState(false);
  const [blockSharesErr, setBlockSharesErr] = useState<string | null>(null);
  const [publicShares, setPublicShares] = useState<DashboardPublicShareRow[]>([]);
  const [publicSharePick, setPublicSharePick] = useState<Record<string, boolean>>({});
  const [publicShareLabel, setPublicShareLabel] = useState("");
  const [publicShareExpiresAt, setPublicShareExpiresAt] = useState("");
  const [publicSharePassword, setPublicSharePassword] = useState("");
  const [publicSharesBusy, setPublicSharesBusy] = useState(false);
  const [publicSharesErr, setPublicSharesErr] = useState<string | null>(null);
  const [createdPublicLink, setCreatedPublicLink] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeHubOverride, setActiveHubOverride] = useState<DashboardHubId | null>(null);
  const [toolCatalogNames, setToolCatalogNames] = useState<string[]>([]);
  const [toolsCatalogErr, setToolsCatalogErr] = useState<string | null>(null);
  const [manualToolName, setManualToolName] = useState("");
  const [pinModalOpen, setPinModalOpen] = useState(false);
  const [pinSourceBlockId, setPinSourceBlockId] = useState<string | null>(null);
  const [pinTargetId, setPinTargetId] = useState("");
  const [pinBusy, setPinBusy] = useState(false);
  const [templateBusy, setTemplateBusy] = useState(false);

  const selectedIdRef = useRef<string | null>(selectedId);
  selectedIdRef.current = selectedId;

  /** Never render blocks/chat from `detail` unless it matches the selected dashboard id. */
  const dashboardReady = Boolean(selectedId && detail && detail.id === selectedId);

  const accessRole = detail?.access_role ?? "owner";
  const isViewer = accessRole === "viewer";
  const isPrimaryOwner = accessRole === "owner";
  const canManageMembers = accessRole === "owner" || accessRole === "co_owner";
  const canEditContent = !isViewer;

  const pinTargetOptions = useMemo(
    () =>
      list.filter(
        (w) =>
          w.id !== selectedId &&
          w.access_role !== "viewer" &&
          (w.access_role === "owner" ||
            w.access_role === "editor" ||
            w.access_role === "co_owner" ||
            !w.access_role),
      ),
    [list, selectedId],
  );

  const uiLayout = useMemo(() => asUiLayout(detail?.ui_layout), [detail]);
  const gridLayout = useMemo(
    () => (layoutEditMode ? layoutDraft : uiLayout ?? { version: 1, blocks: [] }),
    [layoutEditMode, layoutDraft, uiLayout]
  );

  const agentSystemPromptExtra = useMemo(() => {
    const raw = data._agentlayer;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return "";
    const al = raw as DashboardDataAgentlayer;
    const s =
      typeof al.system_prompt_extra === "string"
        ? al.system_prompt_extra
        : typeof al.instructions === "string"
          ? al.instructions
          : "";
    return s;
  }, [data]);

  const dashboardToolAllowlist = useMemo(() => {
    const raw = data._agentlayer;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
    const al = raw as DashboardDataAgentlayer;
    const arr = al.tool_allowlist ?? al.allowed_tools;
    if (!Array.isArray(arr)) return [];
    return [...new Set(arr.map((x) => String(x).trim()).filter(Boolean))].sort((a, b) =>
      a.localeCompare(b)
    );
  }, [data]);

  const pickableCatalogTools = useMemo(
    () => toolCatalogNames.filter((n) => !dashboardToolAllowlist.includes(n)),
    [toolCatalogNames, dashboardToolAllowlist]
  );

  const installableCatalog = useMemo(
    () => kindCatalog.filter((r) => r.has_schema),
    [kindCatalog]
  );

  const installedKindSet = useMemo(() => {
    if (!Array.isArray(installedTemplateKinds)) return new Set<string>();
    return new Set(installedTemplateKinds);
  }, [installedTemplateKinds]);

  const kindsAllowedForNewDashboard = useMemo(() => {
    const rows = kindCatalog.filter(
      (r) => r.kind === "custom" || (r.has_template && installedKindSet.has(r.kind))
    );
    const custom = rows.find((r) => r.kind === "custom");
    const rest = rows.filter((r) => r.kind !== "custom").sort((a, b) => a.kind.localeCompare(b.kind));
    if (custom) return [custom, ...rest];
    const synthetic: KindCatalogRow = {
      kind: "custom",
      label: t("dashboard:customKindLabel"),
      description: "",
      has_template: true,
      has_schema: true,
    };
    return [synthetic, ...rest];
  }, [kindCatalog, installedKindSet, t]);

  const loadList = useCallback(async () => {
    setError(null);
    const res = await apiFetch("/v1/dashboards", auth);
    if (!res.ok) {
      setError(await res.text());
      setList([]);
      setSchemaInstalled(null);
      setInstalledTemplateKinds(null);
      return;
    }
    const j = (await res.json()) as {
      dashboards?: DashboardSummary[];
      schema_installed?: boolean;
      kind_catalog?: unknown;
      installed_template_kinds?: unknown;
    };
    setList(j.dashboards || []);
    const installed = typeof j.schema_installed === "boolean" ? j.schema_installed : true;
    setSchemaInstalled(installed);
    setKindCatalog(parseKindCatalog(j.kind_catalog));
    if (!installed) setInstalledTemplateKinds([]);
    else setInstalledTemplateKinds(normalizeKindList(j.installed_template_kinds));
  }, [auth]);

  const runInstallSingle = useCallback(
    async (kind: string) => {
      setError(null);
      setInstallBusy(true);
      try {
        const res = await apiFetch("/v1/dashboards/install", auth, {
          method: "POST",
          body: JSON.stringify({ kinds: [kind] }),
        });
        if (!res.ok) {
          setError(await res.text());
          return;
        }
        setInstallModalRow(null);
        await loadList();
      } finally {
        setInstallBusy(false);
      }
    },
    [auth, loadList]
  );

  const runInstallTemplates = useCallback(
    async (kind: string) => {
      setError(null);
      setInstallBusy(true);
      try {
        const res = await apiFetch("/v1/dashboards/install-templates", auth, {
          method: "POST",
          body: JSON.stringify({ kinds: [kind] }),
        });
        if (!res.ok) {
          setError(await res.text());
          return;
        }
        setInstallModalRow(null);
        await loadList();
      } finally {
        setInstallBusy(false);
      }
    },
    [auth, loadList]
  );

  useEffect(() => {
    if (!installModalRow) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !installBusy) setInstallModalRow(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [installModalRow, installBusy]);

  const loadDetail = useCallback(
    async (id: string) => {
      setError(null);
      const res = await apiFetch(`/v1/dashboards/${id}`, auth);
      if (selectedIdRef.current !== id) return;
      if (!res.ok) {
        setError(await res.text());
        setDetail(null);
        return;
      }
      const j = (await res.json()) as { dashboard?: DashboardDetail };
      const w = j.dashboard;
      if (selectedIdRef.current !== id) return;
      if (!w) {
        setDetail(null);
        return;
      }
      setDetail(w);
      setTitle(w.title || "");
      setData(w.data && typeof w.data === "object" ? { ...w.data } : {});
    },
    [auth]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      await loadList();
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [loadList]);

  useLayoutEffect(() => {
    setLayoutEditMode(false);
    setOnboardingHidden(false);
    if (!selectedId) {
      setDetail(null);
      setData({});
      setTitle("");
      setLayoutDraft({ version: 1, blocks: [] });
      return;
    }
    void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    if (!detail || layoutEditMode) return;
    const ul = asUiLayout(detail.ui_layout);
    setLayoutDraft(ul ?? { version: 1, blocks: [] });
  }, [detail, layoutEditMode]);

  useEffect(() => {
    if (detail?.access_role === "viewer") setLayoutEditMode(false);
  }, [detail?.access_role]);

  useEffect(() => {
    if (!selectedId || !canManageMembers) {
      setMembers([]);
      setMembersErr(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/members`, auth);
      if (!res.ok) {
        if (!cancelled) setMembersErr(await res.text());
        return;
      }
      const j = (await res.json()) as { members?: DashboardMemberRow[] };
      if (!cancelled) {
        setMembersErr(null);
        setMembers(j.members ?? []);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, canManageMembers, auth]);

  useEffect(() => {
    if (!selectedId || !canManageMembers) {
      setBlockGrants([]);
      setBlockSharesErr(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/block-shares`, auth);
      if (!res.ok) {
        if (!cancelled) setBlockSharesErr(await res.text());
        return;
      }
      const j = (await res.json()) as { grants?: DashboardBlockGrantRow[] };
      if (!cancelled) {
        setBlockSharesErr(null);
        setBlockGrants(j.grants ?? []);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, canManageMembers, auth]);

  useEffect(() => {
    if (!selectedId || !canManageMembers) {
      setPublicShares([]);
      setPublicSharesErr(null);
      setCreatedPublicLink(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/public-shares`, auth);
      if (!res.ok) {
        if (!cancelled) setPublicSharesErr(await res.text());
        return;
      }
      const j = (await res.json()) as { shares?: DashboardPublicShareRow[] };
      if (!cancelled) {
        setPublicSharesErr(null);
        setPublicShares(j.shares ?? []);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, canManageMembers, auth]);

  useEffect(() => {
    if (!settingsOpen || !detail) return;
    let cancelled = false;
    setToolsCatalogErr(null);
    void (async () => {
      try {
        const res = await apiFetch("/v1/tools", auth);
        if (!res.ok) {
          if (!cancelled) setToolsCatalogErr(await res.text());
          return;
        }
        const j = (await res.json()) as { tools?: Array<{ function?: { name?: string } }> };
        const names: string[] = [];
        for (const t of j.tools ?? []) {
          const n = t?.function?.name;
          if (typeof n === "string" && n.trim()) names.push(n.trim());
        }
        if (!cancelled) {
          setToolCatalogNames([...new Set(names)].sort((a, b) => a.localeCompare(b)));
        }
      } catch (e) {
        if (!cancelled) setToolsCatalogErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [settingsOpen, detail, auth]);

  const recentActivity = useMemo(() => {
    return [...list]
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      .slice(0, 5);
  }, [list]);

  const groupedByHub = useMemo(() => groupDashboardsByHub(list), [list]);
  const selectedHubId = useMemo(
    () => hubForSelectedId(groupedByHub, selectedId),
    [groupedByHub, selectedId]
  );
  const effectiveHubId = activeHubOverride ?? selectedHubId ?? "other";

  // Clear hub-tab override only when the selected dashboard changes — not when the user
  // picks another hub tab while a dashboard stays open (that was resetting to Pets, etc.).
  useEffect(() => {
    setActiveHubOverride(null);
  }, [selectedId]);

  const catalogRows = useMemo(() => {
    const q = catalogQuery.trim().toLowerCase();
    return installableCatalog.filter((r) => {
      if (!q) return true;
      return (
        r.kind.includes(q) ||
        r.label.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q)
      );
    });
  }, [installableCatalog, catalogQuery]);

  const addDashboardMember = async () => {
    if (!selectedId || !memberEmail.trim()) return;
    setMembersBusy(true);
    setMembersErr(null);
    try {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/members`, auth, {
        method: "POST",
        body: JSON.stringify({ email: memberEmail.trim().toLowerCase(), role: memberRole }),
      });
      const raw = await res.text();
      if (!res.ok) {
        setMembersErr(raw);
        return;
      }
      let j: { members?: DashboardMemberRow[] } = {};
      try {
        j = JSON.parse(raw) as { members?: DashboardMemberRow[] };
      } catch {
        j = {};
      }
      setMembers(j.members ?? []);
      setMemberEmail("");
    } catch (e) {
      setMembersErr(e instanceof Error ? e.message : String(e));
    } finally {
      setMembersBusy(false);
    }
  };

  const removeDashboardMember = async (userId: string) => {
    if (!selectedId) return;
    setMembersBusy(true);
    setMembersErr(null);
    try {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/members/${userId}`, auth, {
        method: "DELETE",
      });
      if (!res.ok) {
        setMembersErr(await res.text());
        return;
      }
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
    } finally {
      setMembersBusy(false);
    }
  };

  const addBlockShareGrant = async () => {
    if (!selectedId || !blockShareEmail.trim()) return;
    const ids = Object.entries(blockSharePick)
      .filter(([, v]) => v)
      .map(([k]) => k);
    if (ids.length === 0) {
      setBlockSharesErr(t("dashboard:selectAtLeastOneBlock"));
      return;
    }
    setBlockSharesBusy(true);
    setBlockSharesErr(null);
    try {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/block-shares`, auth, {
        method: "POST",
        body: JSON.stringify({
          email: blockShareEmail.trim().toLowerCase(),
          block_ids: ids,
          permission: blockSharePermission,
        }),
      });
      const raw = await res.text();
      if (!res.ok) {
        setBlockSharesErr(raw);
        return;
      }
      const j = JSON.parse(raw) as { grants?: DashboardBlockGrantRow[] };
      setBlockGrants(j.grants ?? []);
      setBlockShareEmail("");
      setBlockSharePermission("view");
      setBlockSharePick({});
    } catch (e) {
      setBlockSharesErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBlockSharesBusy(false);
    }
  };

  const removeBlockGrant = async (userId: string) => {
    if (!selectedId) return;
    setBlockSharesBusy(true);
    setBlockSharesErr(null);
    try {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/block-shares/${userId}`, auth, {
        method: "DELETE",
      });
      if (!res.ok) {
        setBlockSharesErr(await res.text());
        return;
      }
      setBlockGrants((prev) => prev.filter((g) => g.user_id !== userId));
    } finally {
      setBlockSharesBusy(false);
    }
  };

  const openPinModal = (blockId: string) => {
    setPinSourceBlockId(blockId);
    const preferred =
      pinTargetOptions.find((w) => w.kind === "personal_dashboard")?.id ||
      pinTargetOptions[0]?.id ||
      "";
    setPinTargetId(preferred);
    setPinModalOpen(true);
  };

  const confirmPinBlock = async () => {
    if (!selectedId || !pinSourceBlockId || !pinTargetId) return;
    setPinBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/v1/dashboards/${pinTargetId}/pin-block`, auth, {
        method: "POST",
        body: JSON.stringify({
          source_dashboard_id: selectedId,
          source_block_id: pinSourceBlockId,
        }),
      });
      if (!res.ok) {
        setError(await res.text());
        return;
      }
      setPinModalOpen(false);
      setPinSourceBlockId(null);
      alert(t("dashboard:pinBlockSuccess"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("dashboard:pinBlockFailed"));
    } finally {
      setPinBusy(false);
    }
  };

  const exportTemplate = async () => {
    if (!selectedId) return;
    setTemplateBusy(true);
    try {
      const res = await apiFetch(`/v1/dashboards/${selectedId}/export-template`, auth);
      if (!res.ok) {
        setError(await res.text());
        return;
      }
      const j = await res.json();
      const text = JSON.stringify(j.template ?? j, null, 2);
      await navigator.clipboard.writeText(text);
      alert(t("dashboard:templateExportDone"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTemplateBusy(false);
    }
  };

  const importTemplateFile = async (file: File) => {
    setTemplateBusy(true);
    setError(null);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as {
        kind?: string;
        title?: string;
        ui_layout?: Record<string, unknown>;
        initial_data?: Record<string, unknown>;
      };
      const res = await apiFetch("/v1/dashboards/from-template", auth, {
        method: "POST",
        body: JSON.stringify({
          kind: parsed.kind || "custom",
          title: parsed.title || "Imported dashboard",
          ui_layout: parsed.ui_layout || parsed,
          initial_data: parsed.initial_data,
        }),
      });
      if (!res.ok) {
        setError(await res.text());
        return;
      }
      const j = (await res.json()) as { dashboard?: DashboardDetail & { id: string } };
      if (j.dashboard?.id) {
        await loadList();
        setSelectedId(j.dashboard.id);
        alert(t("dashboard:templateImportDone"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTemplateBusy(false);
    }
  };

  const createPublicShare = async () => {
    if (!selectedId) return;
    setPublicSharesBusy(true);
    setPublicSharesErr(null);
    setCreatedPublicLink(null);
    try {
      const ids = Object.entries(publicSharePick)
        .filter(([, v]) => v)
        .map(([k]) => k);
      let expiresIso: string | undefined;
      if (publicShareExpiresAt.trim()) {
        const d = new Date(publicShareExpiresAt);
        if (Number.isNaN(d.getTime())) {
          setPublicSharesErr(t("dashboard:publicShareExpiresInvalid"));
          return;
        }
        expiresIso = d.toISOString();
      }
      const pw = publicSharePassword.trim();
      if (pw && pw.length < 4) {
        setPublicSharesErr(t("dashboard:publicSharePasswordTooShort"));
        return;
      }
      const res = await apiFetch(`/v1/dashboards/${selectedId}/public-shares`, auth, {
        method: "POST",
        body: JSON.stringify({
          block_ids: ids,
          label: publicShareLabel.trim(),
          expires_at: expiresIso,
          password: pw || undefined,
        }),
      });
      const raw = await res.text();
      if (!res.ok) {
        setPublicSharesErr(raw);
        return;
      }
      const j = JSON.parse(raw) as {
        share?: DashboardPublicShareRow;
        token?: string;
      };
      if (j.share) {
        setPublicShares((prev) => [j.share!, ...prev]);
      }
      if (j.token) {
        setCreatedPublicLink(`/app/dashboard/shared?t=${j.token}`);
      }
      setPublicShareLabel("");
      setPublicShareExpiresAt("");
      setPublicSharePassword("");
      setPublicSharePick({});
    } catch (e) {
      setPublicSharesErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPublicSharesBusy(false);
    }
  };

  const revokePublicShare = async (shareId: string) => {
    if (!selectedId) return;
    setPublicSharesBusy(true);
    setPublicSharesErr(null);
    try {
      const res = await apiFetch(
        `/v1/dashboards/${selectedId}/public-shares/${shareId}`,
        auth,
        { method: "DELETE" }
      );
      if (!res.ok) {
        setPublicSharesErr(await res.text());
        return;
      }
      setPublicShares((prev) =>
        prev.map((s) =>
          s.id === shareId ? { ...s, revoked_at: new Date().toISOString() } : s
        )
      );
    } finally {
      setPublicSharesBusy(false);
    }
  };

  const copyPublicShareUrl = async (urlPath: string) => {
    const full = `${window.location.origin}${urlPath}`;
    try {
      await navigator.clipboard.writeText(full);
    } catch {
      window.prompt(t("dashboard:publicShareCopyPrompt"), full);
    }
  };

  const save = async () => {
    if (!selectedId || !detail || !canEditContent) return;
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        title: title.trim() || detail.title,
        data,
      };
      if (layoutEditMode) {
        body.ui_layout = layoutDraft;
      }
      const res = await apiFetch(`/v1/dashboards/${selectedId}`, auth, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        setError(await res.text());
        return;
      }
      const j = (await res.json()) as { dashboard?: DashboardDetail };
      if (j.dashboard) {
        setDetail(j.dashboard);
        setData(
          j.dashboard.data && typeof j.dashboard.data === "object" ? { ...j.dashboard.data } : {}
        );
        setLayoutEditMode(false);
        const ul = asUiLayout(j.dashboard.ui_layout);
        setLayoutDraft(ul ?? { version: 1, blocks: [] });
      }
      await loadList();
    } finally {
      setSaving(false);
    }
  };

  const startLayoutEdit = () => {
    if (!detail) return;
    const ul = asUiLayout(detail.ui_layout) ?? { version: 1, blocks: [] };
    setLayoutDraft(JSON.parse(JSON.stringify(ul)) as UiLayout);
    setLayoutEditMode(true);
  };

  const cancelLayoutEdit = () => {
    if (!detail) {
      setLayoutEditMode(false);
      return;
    }
    setLayoutEditMode(false);
    const ul = asUiLayout(detail.ui_layout) ?? { version: 1, blocks: [] };
    setLayoutDraft(ul);
    setData(detail.data && typeof detail.data === "object" ? { ...detail.data } : {});
  };

  const createWs = async (kind: string) => {
    setError(null);
    const res = await apiFetch("/v1/dashboards", auth, {
      method: "POST",
      body: JSON.stringify({
        kind,
        title: labelForKind(kind, kindCatalog),
      }),
    });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    const j = (await res.json()) as { dashboard?: DashboardDetail & { id: string } };
    if (j.dashboard?.id) {
      setNewWsModalOpen(false);
      setHubPanel("home");
      await loadList();
      setLayoutEditMode(false);
      setDetail(j.dashboard as DashboardDetail);
      setData(
        j.dashboard.data && typeof j.dashboard.data === "object" ? { ...j.dashboard.data } : {}
      );
      setTitle(j.dashboard.title || labelForKind(kind, kindCatalog));
      setError(null);
      const ul = asUiLayout(j.dashboard.ui_layout);
      setLayoutDraft(ul ?? { version: 1, blocks: [] });
      setSelectedId(j.dashboard.id);
      setOnboardingHidden(false);
    }
  };

  const removeWs = async () => {
    if (!selectedId || !isPrimaryOwner) return;
    if (!window.confirm(t("dashboard:dashboardDeleteConfirm"))) return;
    const res = await apiFetch(`/v1/dashboards/${selectedId}`, auth, {
      method: "DELETE",
    });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    setSelectedId(null);
    await loadList();
  };

  const openCatalog = () => {
    setSelectedId(null);
    setHubPanel("catalog");
    setActionsSidebarOpen(false);
  };

  const selectDashboard = (id: string) => {
    if (id === selectedId) {
      void markDashboardSeen(id);
      return;
    }
    setLayoutEditMode(false);
    setDetail(null);
    setData({});
    setTitle("");
    setError(null);
    setLayoutDraft({ version: 1, blocks: [] });
    setSelectedId(id);
    setHubPanel("home");
    setActionsSidebarOpen(false);
    void markDashboardSeen(id);
  };

  const markBlockSeen = useCallback(
    (blockId: string) => {
      if (!selectedId || !blockId.trim()) return;
      void markDashboardSeen(selectedId, [blockId.trim()]).then(() => refreshSummary());
    },
    [selectedId, markDashboardSeen, refreshSummary]
  );

  useEffect(() => {
    const id = searchParams.get("id")?.trim();
    if (!id || loading) return;
    if (list.some((w) => w.id === id) && id !== selectedId) {
      selectDashboard(id);
    }
  }, [searchParams, list, loading, selectedId]);

  useEffect(() => {
    if (!dashboardReady || !highlightBlockId) return;
    const el = document.querySelector(`[data-block-id="${CSS.escape(highlightBlockId)}"]`);
    if (el) {
      window.setTimeout(() => {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 120);
    }
  }, [dashboardReady, highlightBlockId, gridLayout.blocks.length]);

  const addToolToDashboardAllowlist = useCallback(
    (name: string) => {
      const t = name.trim();
      if (!t || !canEditContent) return;
      setData((prev) => {
        const next = { ...prev } as Record<string, unknown>;
        const prevAl = next._agentlayer;
        const merged: Record<string, unknown> =
          prevAl && typeof prevAl === "object" && !Array.isArray(prevAl) ? { ...prevAl } : {};
        const cur = merged.tool_allowlist;
        const list = Array.isArray(cur) ? cur.map((x) => String(x).trim()).filter(Boolean) : [];
        if (list.includes(t)) return prev;
        merged.tool_allowlist = [...list, t];
        next._agentlayer = merged;
        return next;
      });
    },
    [canEditContent]
  );

  const removeToolFromDashboardAllowlist = useCallback(
    (name: string) => {
      if (!canEditContent) return;
      setData((prev) => {
        const next = { ...prev } as Record<string, unknown>;
        const prevAl = next._agentlayer;
        if (!prevAl || typeof prevAl !== "object" || Array.isArray(prevAl)) return prev;
        const merged = { ...prevAl } as Record<string, unknown>;
        const cur = merged.tool_allowlist;
        const list = Array.isArray(cur) ? cur.map((x) => String(x).trim()).filter(Boolean) : [];
        merged.tool_allowlist = list.filter((x) => x !== name);
        next._agentlayer = merged;
        return next;
      });
    },
    [canEditContent]
  );

  const confirmInstallCatalogRow = (row: KindCatalogRow) => {
    if (!row.has_schema) return;
    setInstallModalRow(row);
  };

  const runInstallFromModal = () => {
    if (!installModalRow) return;
    if (schemaInstalled) void runInstallTemplates(installModalRow.kind);
    else void runInstallSingle(installModalRow.kind);
  };

  if (!loading && schemaInstalled === false) {
    return (
      <div className="h-full min-h-0 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-10">
          <h1 className="text-xl font-semibold text-white">{t("dashboard:catalogTitle")}</h1>
          <p className="mt-1 text-sm text-surface-muted">
            {t("dashboard:catalogIntro")}
          </p>

          {installableCatalog.length === 0 ? (
            <p className="mt-8 text-sm text-surface-muted">{t("dashboard:noInstallablePacks")}</p>
          ) : (
            <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {installableCatalog.map((row) => (
                <li key={row.kind}>
                  <button
                    type="button"
                    onClick={() => confirmInstallCatalogRow(row)}
                    className="flex h-full min-h-[148px] w-full flex-col rounded-xl border border-surface-border bg-surface-raised p-5 text-left transition hover:border-sky-500/35 hover:bg-white/[0.03]"
                  >
                    <span className="text-base font-medium text-white">{row.label}</span>
                    {row.description ? (
                      <span className="mt-2 text-sm leading-snug text-surface-muted">{row.description}</span>
                    ) : null}
                    <span className="mt-auto pt-4 text-sm font-medium text-sky-400">{t("dashboard:install")}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error ? (
            <div className="mt-6 rounded-lg border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
              {error}
            </div>
          ) : null}
        </div>

        {installModalRow ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
            <div
              className="absolute inset-0 bg-black/70"
              role="button"
              tabIndex={0}
              aria-label={t("dashboard:close")}
              onClick={() => {
                if (!installBusy) setInstallModalRow(null);
              }}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && !installBusy) {
                  e.preventDefault();
                  setInstallModalRow(null);
                }
              }}
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="ws-install-title"
              className="relative w-full max-w-md rounded-xl border border-surface-border bg-surface-raised p-6 shadow-xl"
            >
              <h2 id="ws-install-title" className="text-lg font-semibold text-white">
                {t("dashboard:installPackConfirmTitle", { label: installModalRow.label })}
              </h2>
              {installModalRow.description ? (
                <p className="mt-2 text-sm text-surface-muted">{installModalRow.description}</p>
              ) : null}
              <p className="mt-3 text-sm text-surface-muted">
                {t("dashboard:installPackConfirmBody")}
              </p>
              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  disabled={installBusy}
                  className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-50"
                  onClick={() => setInstallModalRow(null)}
                >
                  {t("admin:cancel")}
                </button>
                <button
                  type="button"
                  disabled={installBusy || !installModalRow.has_schema}
                  className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void runInstallFromModal()}
                >
                  {installBusy ? t("dashboard:installing") : t("dashboard:install")}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  if (loading || schemaInstalled === null) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-surface-muted">
        {t("dashboard:loading")}
      </div>
    );
  }

  const dashboardActionsSidebar = (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex flex-col gap-1 p-2">
        <p className="px-2.5 pt-1 text-xs font-semibold uppercase tracking-wide text-surface-muted">
          {t("dashboard:actions")}
        </p>
        <button
          type="button"
          onClick={() => {
            setNewWsModalOpen(true);
            setHubPanel("home");
            setSelectedId(null);
            setActionsSidebarOpen(false);
          }}
          className="rounded-lg px-2.5 py-2 text-left text-xs text-neutral-200 transition hover:bg-white/5"
        >
          {t("dashboard:createNew")}
        </button>
        <button
          type="button"
          onClick={() => {
            setSelectedId(null);
            setHubPanel("overview");
            setActionsSidebarOpen(false);
          }}
          className={[
            "rounded-lg px-2.5 py-2 text-left text-xs transition hover:bg-white/5",
            !selectedId && hubPanel === "overview" ? "bg-white/10 text-white" : "text-neutral-200",
          ].join(" ")}
        >
          {t("dashboard:overviewTitle")}
        </button>
        <button
          type="button"
          disabled
          className="cursor-not-allowed rounded-lg px-2.5 py-2 text-left text-xs text-white/30"
          title={t("dashboard:comingSoon")}
        >
          {t("dashboard:import")}
        </button>
        <button
          type="button"
          onClick={() => openCatalog()}
          className={[
            "rounded-lg px-2.5 py-2 text-left text-xs transition hover:bg-white/5",
            !selectedId && hubPanel === "catalog" ? "bg-white/10 text-white" : "text-neutral-200",
          ].join(" ")}
        >
          {t("dashboard:catalogTitle")}
        </button>
      </div>
    </div>
  );

  const overviewMain = (
    <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
      {error ? (
        <div className="mb-4 rounded-lg border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      ) : null}
      <DashboardOverviewPanel
        list={list}
        kindLabelFor={(k) => subtitleForDashboardKind(k, kindCatalog)}
        onOpenDashboard={(id) => selectDashboard(id)}
        dashboardUnreadCount={dashboardUnreadCount}
      />
    </div>
  );

  const hubHomeMain = (
    <div className="mx-auto max-w-3xl space-y-8 py-6">
      <DashboardHubNavigator
        hubs={DEFAULT_HUBS}
        grouped={groupedByHub}
        activeHubId={effectiveHubId}
        setActiveHubId={(id) => setActiveHubOverride(id)}
        selectedId={selectedId}
        onSelectDashboard={(id) => selectDashboard(id)}
        kindLabelFor={(k) => subtitleForDashboardKind(k, kindCatalog)}
        dashboardUnreadCount={dashboardUnreadCount}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => setNewWsModalOpen(true)}
          className="flex flex-col rounded-xl border border-surface-border bg-surface-raised p-6 text-left transition hover:border-sky-500/35 hover:bg-white/[0.03]"
        >
          <span className="text-base font-semibold text-white">{t("dashboard:newDashboardTitle")}</span>
          <span className="mt-2 text-sm text-surface-muted">{t("dashboard:newDashboardSubtitle")}</span>
        </button>
        <button
          type="button"
          onClick={() => openCatalog()}
          className="flex flex-col rounded-xl border border-surface-border bg-surface-raised p-6 text-left transition hover:border-sky-500/35 hover:bg-white/[0.03]"
        >
          <span className="text-base font-semibold text-white">{t("dashboard:catalogTitle")}</span>
          <span className="mt-2 text-sm text-surface-muted">{t("dashboard:catalogIntro")}</span>
        </button>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">{t("dashboard:recentActivity")}</p>
        {recentActivity.length === 0 ? (
          <p className="mt-2 text-sm text-surface-muted">{t("dashboard:noActivityYet")}</p>
        ) : (
          <ul className="mt-2 space-y-1.5 text-sm text-neutral-300">
            {recentActivity.map((w) => (
              <li key={w.id}>
                <button
                  type="button"
                  className="w-full rounded-md px-2 py-1.5 text-left hover:bg-white/5"
                  onClick={() => selectDashboard(w.id)}
                >
                  <span className="text-white">{w.title || w.kind}</span>
                  <span className="text-surface-muted"> — {relativeActivityEn(w.updated_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );

  const catalogMain = (
    <div className="min-h-0 flex-1 space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-end gap-3">
        <button
          type="button"
          onClick={() => setHubPanel("home")}
          className="text-sm text-sky-400 hover:text-sky-300"
        >
          {t("dashboard:backToDashboards")}
        </button>
      </div>
      <h1 className="text-xl font-semibold text-white">{t("dashboard:catalogTitle")}</h1>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[200px] flex-1">
          <label className="mb-1 block text-xs text-surface-muted">{t("dashboard:catalogSearchLabel")}</label>
          <input
            value={catalogQuery}
            onChange={(e) => setCatalogQuery(e.target.value)}
            placeholder={t("dashboard:filterByNamePlaceholder")}
            className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-surface-muted">{t("dashboard:catalogCategoryLabel")}</label>
          <select
            disabled
            className="rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white/50"
            value="all"
            onChange={() => {}}
          >
            <option value="all">{t("dashboard:catalogCategoryAll")}</option>
          </select>
        </div>
      </div>
      {catalogRows.length === 0 ? (
        <p className="text-sm text-surface-muted">{t("dashboard:catalogNoMatches")}</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {catalogRows.map((row) => {
            const isInstalled = installedKindSet.has(row.kind);
            return (
              <li
                key={row.kind}
                className="flex flex-col rounded-xl border border-surface-border bg-surface-raised p-5"
              >
                <span className="text-base font-medium text-white">{row.label}</span>
                {row.description ? (
                  <span className="mt-2 text-sm leading-snug text-surface-muted">{row.description}</span>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  {isInstalled ? (
                    <span className="rounded-md border border-white/10 px-2 py-1 text-xs text-surface-muted">
                      {t("dashboard:catalogInstalledBadge")}
                    </span>
                  ) : (
                    <button
                      type="button"
                      disabled={installBusy || !row.has_schema}
                      className="rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                      onClick={() => confirmInstallCatalogRow(row)}
                    >
                      {t("dashboard:install")}
                    </button>
                  )}
                  {isInstalled && row.has_template ? (
                    <button
                      type="button"
                      className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5"
                      onClick={() => void createWs(row.kind)}
                    >
                      {t("dashboard:catalogCreateDashboardBtn")}
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );

  let main: ReactNode;
  if (selectedId) {
    main = (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-surface-border px-4 py-3 md:px-6">
          <p className="text-sm text-surface-muted">
            Dashboard /{" "}
            <span className="text-white">
              {dashboardReady ? detail?.title || title || "…" : "…"}
            </span>
          </p>
        </div>
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:overflow-hidden">
            <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
            {error ? (
              <div className="mb-4 rounded-lg border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
                {error}
              </div>
            ) : null}
            <div className="mb-4">
              <DashboardHubNavigator
                hubs={DEFAULT_HUBS}
                grouped={groupedByHub}
                activeHubId={effectiveHubId}
                setActiveHubId={(id) => setActiveHubOverride(id)}
                selectedId={selectedId}
                onSelectDashboard={(id) => selectDashboard(id)}
                kindLabelFor={(k) => subtitleForDashboardKind(k, kindCatalog)}
              />
            </div>
            {!dashboardReady ? (
            <p className="text-sm text-surface-muted">{t("dashboard:loading")}</p>
            ) : (
              <>
                {isViewer ? (
                  <p className="mb-4 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-surface-muted">
                    {detail?.access_scope === "granular" ? (
                      <>{t("dashboard:viewerReadOnlyGranular")}</>
                    ) : (
                      <>{t("dashboard:viewerReadOnlySimple")}</>
                    )}
                  </p>
                ) : null}
                <div className="mb-4 flex flex-wrap items-end gap-3">
                  <div className="min-w-[200px] flex-1">
                    <label className="mb-1 block text-xs text-surface-muted">{t("dashboard:dashboardTitleLabel")}</label>
                    <input
                      readOnly={isViewer}
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50 read-only:cursor-default read-only:opacity-90"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canEditContent ? (
                      !layoutEditMode ? (
                        <button
                          type="button"
                          className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200 hover:bg-white/5"
                          onClick={() => startLayoutEdit()}
                        >
                          {t("dashboard:editLayout")}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200 hover:bg-white/5"
                          onClick={() => cancelLayoutEdit()}
                        >
                          {t("admin:cancel")}
                        </button>
                      )
                    ) : null}
                    {canEditContent ? (
                      <button
                        type="button"
                        disabled={saving}
                        className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                        onClick={() => void save()}
                      >
                        {saving ? t("dashboard:saving") : t("admin:save")}
                      </button>
                    ) : null}
                    {canEditContent && detail?.kind === "projects" && selectedId ? (
                      <button
                        type="button"
                        className="rounded-lg border border-violet-500/40 bg-violet-950/25 px-4 py-2 text-sm text-violet-100 hover:bg-violet-900/35"
                        onClick={() => setProjectsImportOpen(true)}
                      >
                        {t("dashboard:importFromGithub")}
                      </button>
                    ) : null}
                    {detail ? (
                      <button
                        type="button"
                        className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200 hover:bg-white/5"
                        onClick={() => setSettingsOpen(true)}
                      >
                        Settings
                      </button>
                    ) : null}
                    {isPrimaryOwner ? (
                      <button
                        type="button"
                        className="rounded-lg border border-white/10 px-4 py-2 text-sm text-red-300 hover:bg-red-950/40"
                        onClick={() => void removeWs()}
                      >
                        Delete
                      </button>
                    ) : null}
                  </div>
                </div>
                {canManageMembers ? (
                  <p className="mb-4 text-xs text-surface-muted">
                    {t("dashboard:membersMovedHint")}{" "}
                    <span className="text-white/80">{t("dashboard:settingsLabel")}</span>.
                  </p>
                ) : null}
                <p className="mb-4 text-xs text-surface-muted">
                  Template:{" "}
                  <span className="text-white/80">
                    {subtitleForDashboardKind(detail!.kind, kindCatalog)}
                  </span>
                </p>
                {detail?.onboarding &&
                !isViewer &&
                !onboardingHidden &&
                !isOnboardingDismissed(selectedId!) ? (
                  <DashboardOnboardingBanner
                    dashboardId={selectedId!}
                    onboarding={detail.onboarding}
                    readOnly={isViewer}
                    onStartChat={(msg) => {
                      setChatComposeDraft(msg);
                      setChatComposeDraftSeed((n) => n + 1);
                    }}
                    onDismiss={() => setOnboardingHidden(true)}
                  />
                ) : null}
                <DashboardGridCanvas
                  key={selectedId}
                  layout={gridLayout}
                  setLayout={setLayoutDraft}
                  data={data}
                  setData={setData}
                  editMode={layoutEditMode && canEditContent}
                  contentReadOnly={isViewer}
                  dashboardId={selectedId}
                  unreadBlockIds={selectedId ? blockUnreadIds(selectedId) : undefined}
                  highlightBlockId={highlightBlockId}
                  onBlockSeen={markBlockSeen}
                  onPinBlock={
                    selectedId && pinTargetOptions.length > 0 ? openPinModal : undefined
                  }
                />
              </>
            )}
            </div>
          </div>
          {dashboardReady ? (
            <aside className="flex w-full shrink-0 flex-col border-t border-surface-border bg-[#0d0d0d]/80 lg:min-h-0 lg:w-[min(400px,36vw)] lg:max-w-md lg:border-t-0 lg:border-l lg:border-surface-border">
              <div className="flex min-h-[280px] flex-1 flex-col p-3 md:p-4 lg:min-h-0 lg:max-h-[calc(100vh-7rem)]">
                <DashboardEmbeddedChat
                  key={selectedId}
                  dashboardId={selectedId}
                  dashboardTitle={title || detail?.title}
                  readOnly={isViewer}
                  composeDraft={chatComposeDraft}
                  composeDraftSeed={chatComposeDraftSeed}
                />
              </div>
            </aside>
          ) : null}
        </div>
      </div>
    );
  } else if (hubPanel === "catalog") {
    main = catalogMain;
  } else if (hubPanel === "overview") {
    main = overviewMain;
  } else {
    main = (
      <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        {error ? (
          <div className="mb-4 rounded-lg border border-red-500/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        ) : null}
        {hubHomeMain}
      </div>
    );
  }

  return (
    <>
      <CollapsibleSidebarShell
        className="bg-surface"
        mobileOpen={actionsSidebarOpen}
        onMobileOpenChange={setActionsSidebarOpen}
        sidebarAriaLabel={t("dashboard:actions")}
        closeSidebarAriaLabel={t("dashboard:closeActionsSidebar")}
        desktopWidthClass="md:w-44"
        sidebarSurfaceClass="bg-surface-raised/40"
        sidebar={dashboardActionsSidebar}
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 items-center gap-2 border-b border-surface-border px-4 py-2 md:hidden">
            <button
              type="button"
              className="rounded-lg border border-surface-border bg-black/30 px-2.5 py-1.5 text-[11px] font-medium text-neutral-300 hover:bg-white/10"
              aria-expanded={actionsSidebarOpen}
              aria-label={t("dashboard:openActionsSidebar")}
              onClick={() => setActionsSidebarOpen(true)}
            >
              {t("dashboard:openActionsSidebarShort")}
            </button>
          </div>
          {main}
        </div>
      </CollapsibleSidebarShell>

      {dashboardReady && detail ? (
        <DashboardSettingsDrawer
          open={settingsOpen}
          title={`Settings — ${detail.title || subtitleForDashboardKind(detail.kind, kindCatalog)}`}
          onClose={() => setSettingsOpen(false)}
        >
          <div className="space-y-4">
            <div className="rounded-xl border border-surface-border bg-black/20 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                {t("dashboard:dashboardInfoTitle")}
              </p>
              <div className="mt-2 space-y-1 text-sm text-neutral-200">
                <p>
                  <span className="text-surface-muted">{t("dashboard:dashboardInfoKind")}</span> {detail.kind}
                </p>
                <p>
                  <span className="text-surface-muted">{t("dashboard:dashboardInfoAccess")}</span> {accessRole}
                </p>
                <p>
                  <span className="text-surface-muted">{t("dashboard:dashboardInfoUpdated")}</span> {detail.updated_at}
                </p>
              </div>
            </div>

            {canEditContent ? (
              <div className="rounded-xl border border-surface-border bg-black/20 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                  {t("dashboard:templateExport")} / {t("dashboard:templateImport")}
                </p>
                <p className="mt-1 text-xs text-surface-muted">{t("dashboard:templateImportHint")}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={templateBusy}
                    className="rounded-lg border border-surface-border px-3 py-2 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-50"
                    onClick={() => void exportTemplate()}
                  >
                    {t("dashboard:templateExport")}
                  </button>
                  <label className="cursor-pointer rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500">
                    {t("dashboard:templateImport")}
                    <input
                      type="file"
                      accept="application/json,.json"
                      className="sr-only"
                      disabled={templateBusy}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void importTemplateFile(f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
              </div>
            ) : null}

            <div className="rounded-xl border border-surface-border bg-black/20 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                {t("dashboard:dashboardAgentTitle")}
              </p>
              <p className="mt-2 text-xs text-surface-muted">
                {t("dashboard:dashboardAgentIntro")} {t("dashboard:saveInMainToolbarHint")}
              </p>
              <label className="mt-3 block text-[10px] text-surface-muted" htmlFor="ws-agent-prompt">
                {t("dashboard:dashboardAgentPromptLabel")}
              </label>
              <textarea
                id="ws-agent-prompt"
                readOnly={!canEditContent}
                rows={8}
                value={agentSystemPromptExtra}
                onChange={(e) => {
                  const text = e.target.value;
                  setData((prev) => {
                    const next = { ...prev } as Record<string, unknown>;
                    const prevAl = next._agentlayer;
                    const merged: Record<string, unknown> =
                      prevAl && typeof prevAl === "object" && !Array.isArray(prevAl)
                        ? { ...prevAl }
                        : {};
                    merged.system_prompt_extra = text;
                    next._agentlayer = merged;
                    return next;
                  });
                }}
                placeholder={t("dashboard:agentPromptExtraPlaceholder")}
                className="mt-1 w-full resize-y rounded-lg border border-surface-border bg-black/30 px-3 py-2 font-mono text-sm leading-relaxed text-white outline-none placeholder:text-white/25 focus:border-sky-500/50 read-only:cursor-default read-only:opacity-90"
              />
              <p className="mt-2 text-[10px] text-surface-muted">{t("dashboard:agentPromptExtraSavedHint")}</p>
              <p className="mt-3 text-[11px] text-surface-muted">{t("dashboard:agentPromptScrollHint")}</p>
            </div>

            <div className="rounded-xl border border-surface-border bg-black/20 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                {t("dashboard:dashboardToolPrefsTitle")}
              </p>
              <p className="mt-2 text-xs text-surface-muted">{t("dashboard:dashboardToolPrefsIntro")}</p>
              {toolsCatalogErr ? (
                <p className="mt-2 text-xs text-amber-300/90">
                  {t("dashboard:dashboardToolCatalogErr", { err: toolsCatalogErr })}
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {dashboardToolAllowlist.length === 0 ? (
                  <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-surface-muted">
                    {t("dashboard:dashboardToolDefaultAll")}
                  </span>
                ) : (
                  dashboardToolAllowlist.map((name) => (
                    <span
                      key={name}
                      className="inline-flex max-w-full items-center gap-1 rounded-full border border-sky-500/35 bg-sky-950/50 px-2.5 py-1 text-xs text-sky-100"
                    >
                      <span className="truncate font-mono">{name}</span>
                      {canEditContent ? (
                        <button
                          type="button"
                          className="shrink-0 text-sky-300 hover:text-white"
                          aria-label={t("dashboard:dashboardToolRemoveAria", { name })}
                          onClick={() => removeToolFromDashboardAllowlist(name)}
                        >
                          ×
                        </button>
                      ) : null}
                    </span>
                  ))
                )}
              </div>
              {canEditContent ? (
                <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
                  <div className="min-w-[min(100%,220px)] flex-1">
                    <label className="mb-1 block text-[10px] text-surface-muted" htmlFor="ws-tool-pick">
                      {t("dashboard:dashboardToolFromCatalog")}
                    </label>
                    <select
                      id="ws-tool-pick"
                      disabled={pickableCatalogTools.length === 0}
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                      defaultValue=""
                      onChange={(e) => {
                        const v = e.currentTarget.value;
                        if (v) {
                          addToolToDashboardAllowlist(v);
                          e.currentTarget.selectedIndex = 0;
                        }
                      }}
                    >
                      <option value="">{t("dashboard:dashboardToolPickPlaceholder")}</option>
                      {pickableCatalogTools.map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="min-w-[min(100%,200px)] flex-1">
                    <label className="mb-1 block text-[10px] text-surface-muted" htmlFor="ws-tool-manual">
                      {t("dashboard:dashboardToolManualLabel")}
                    </label>
                    <div className="flex gap-2">
                      <input
                        id="ws-tool-manual"
                        value={manualToolName}
                        onChange={(e) => setManualToolName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            addToolToDashboardAllowlist(manualToolName);
                            setManualToolName("");
                          }
                        }}
                        placeholder={t("dashboard:shareToolNamePlaceholder")}
                        className="min-w-0 flex-1 rounded-lg border border-surface-border bg-black/30 px-3 py-2 font-mono text-sm text-white outline-none focus:border-sky-500/50"
                      />
                      <button
                        type="button"
                        className="shrink-0 rounded-lg border border-surface-border px-3 py-2 text-sm text-neutral-200 hover:bg-white/5"
                        onClick={() => {
                          addToolToDashboardAllowlist(manualToolName);
                          setManualToolName("");
                        }}
                      >
                        {t("dashboard:dashboardToolAdd")}
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-xs text-surface-muted">{t("dashboard:dashboardToolEditorOnly")}</p>
              )}
              <p className="mt-2 text-[10px] text-surface-muted">{t("dashboard:dashboardToolAllowlistMeta")}</p>
            </div>

            {canManageMembers ? (
              <>
              <div className="rounded-xl border border-surface-border bg-black/20 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                  {t("dashboard:membersTitle")}
                </p>
                <p className="mt-1 text-xs text-surface-muted">{t("dashboard:membersIntro")}</p>
                {membersErr ? <p className="mt-2 text-xs text-red-300">{membersErr}</p> : null}
                <div className="mt-3 flex flex-wrap items-end gap-2">
                  <div className="min-w-[220px] flex-1">
                    <label className="mb-1 block text-[10px] text-surface-muted">
                      {t("dashboard:membersEmailLabel")}
                    </label>
                    <input
                      type="email"
                      value={memberEmail}
                      onChange={(e) => setMemberEmail(e.target.value)}
                      placeholder={t("dashboard:shareEmailPlaceholder")}
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10px] text-surface-muted">
                      {t("dashboard:membersRoleLabel")}
                    </label>
                    <select
                      value={memberRole}
                      onChange={(e) => setMemberRole(e.target.value as "viewer" | "editor" | "co_owner")}
                      className="rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white"
                    >
                      <option value="viewer">{t("dashboard:membersRoleViewer")}</option>
                      <option value="editor">{t("dashboard:membersRoleEditor")}</option>
                      <option value="co_owner">{t("dashboard:membersRoleCoOwner")}</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    disabled={membersBusy || !memberEmail.trim()}
                    className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                    onClick={() => void addDashboardMember()}
                  >
                    {membersBusy ? "…" : t("dashboard:membersAdd")}
                  </button>
                </div>
                {members.length === 0 ? (
                  <p className="mt-3 text-xs text-surface-muted">{t("dashboard:membersNoneYet")}</p>
                ) : (
                  <ul className="mt-3 divide-y divide-white/5 text-sm">
                    {members.map((m) => (
                      <li
                        key={m.user_id}
                        className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0"
                      >
                        <span className="text-neutral-200">
                          {m.email} <span className="text-surface-muted">({m.role})</span>
                        </span>
                        <button
                          type="button"
                          disabled={membersBusy}
                          className="text-xs text-red-300 hover:underline disabled:opacity-50"
                          onClick={() => void removeDashboardMember(m.user_id)}
                        >
                          {t("dashboard:remove")}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="mt-4 rounded-xl border border-surface-border bg-black/20 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                  {t("admin:dashboardBlockSharingTitle")}
                </p>
                <p className="mt-1 text-xs text-surface-muted">
                  <span className="text-white/85">{t("dashboard:blockSharingIntroPrefix")}</span>{" "}
                  {t("dashboard:blockSharingIntroBody")}
                </p>
                <p className="mt-2 text-xs text-sky-200/80">{t("dashboard:blockSharingListHint")}</p>
                {blockSharesErr ? <p className="mt-2 text-xs text-red-300">{blockSharesErr}</p> : null}
                <div className="mt-3 flex flex-wrap items-end gap-2">
                  <div className="min-w-[200px] flex-1">
                    <label className="mb-1 block text-[10px] text-surface-muted">
                      {t("dashboard:blockShareUserEmailLabel")}
                    </label>
                    <input
                      type="email"
                      value={blockShareEmail}
                      onChange={(e) => setBlockShareEmail(e.target.value)}
                      placeholder={t("dashboard:shareEmailPlaceholder")}
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50"
                    />
                  </div>
                  <div className="min-w-[140px]">
                    <label className="mb-1 block text-[10px] text-surface-muted">
                      {t("dashboard:blockShareAccessLabel")}
                    </label>
                    <select
                      value={blockSharePermission}
                      onChange={(e) =>
                        setBlockSharePermission(e.target.value === "edit" ? "edit" : "view")
                      }
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/50"
                    >
                      <option value="view">{t("dashboard:blockShareViewOnly")}</option>
                      <option value="edit">{t("dashboard:blockShareEdit")}</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    disabled={blockSharesBusy || !blockShareEmail.trim()}
                    className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                    onClick={() => void addBlockShareGrant()}
                  >
                    {blockSharesBusy ? "…" : t("dashboard:shareSelectedBlocks")}
                  </button>
                </div>
                <p className="mt-3 text-[10px] uppercase tracking-wide text-surface-muted">
                  {t("dashboard:blocksToInclude")}
                </p>
                {gridLayout.blocks.length === 0 ? (
                  <p className="mt-1 text-xs text-surface-muted">{t("dashboard:noBlocksInLayoutYet")}</p>
                ) : (
                  <ul className="mt-2 max-h-48 space-y-2 overflow-y-auto rounded-lg border border-white/5 p-2 text-sm">
                    {gridLayout.blocks.map((b) => {
                      const id = typeof b.id === "string" ? b.id : String(b.id ?? "");
                      const props = b.props && typeof b.props === "object" && !Array.isArray(b.props) ? b.props as { title?: string } : {};
                      const label = props.title?.trim() || b.type || id;
                      if (!id) return null;
                      return (
                        <li key={id} className="flex items-center gap-2">
                          <input
                            id={`bshare-${id}`}
                            type="checkbox"
                            checked={!!blockSharePick[id]}
                            onChange={(e) =>
                              setBlockSharePick((prev) => ({ ...prev, [id]: e.target.checked }))
                            }
                            className="rounded border-surface-border"
                          />
                          <label htmlFor={`bshare-${id}`} className="cursor-pointer text-neutral-200">
                            <span className="text-surface-muted">{b.type}</span> · {label}
                            <span className="ml-2 font-mono text-[10px] text-surface-muted">{id.slice(0, 8)}…</span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {blockGrants.length === 0 ? (
                  <p className="mt-3 text-xs text-surface-muted">{t("dashboard:granularSharesNoneYet")}</p>
                ) : (
                  <ul className="mt-3 divide-y divide-white/5 text-sm">
                    {blockGrants.map((g) => (
                      <li
                        key={g.user_id}
                        className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0"
                      >
                        <span className="text-neutral-200">
                          {g.email}{" "}
                          <span className="text-surface-muted">
                            ({g.block_ids.length} block{g.block_ids.length === 1 ? "" : "s"},{" "}
                            {g.permission === "edit" ? "edit" : "view"})
                          </span>
                        </span>
                        <button
                          type="button"
                          disabled={blockSharesBusy}
                          className="text-xs text-red-300 hover:underline disabled:opacity-50"
                          onClick={() => void removeBlockGrant(g.user_id)}
                        >
                          {t("dashboard:remove")}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="mt-4 rounded-xl border border-violet-500/25 bg-violet-950/15 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-violet-200/90">
                  {t("dashboard:publicShareTitle")}
                </p>
                <p className="mt-1 text-xs text-surface-muted">{t("dashboard:publicShareIntro")}</p>
                {publicSharesErr ? <p className="mt-2 text-xs text-red-300">{publicSharesErr}</p> : null}
                {createdPublicLink ? (
                  <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs text-emerald-100">
                    <p className="font-medium">{t("dashboard:publicShareCreatedOnce")}</p>
                    <p className="mt-2 break-all font-mono text-[11px] text-emerald-50/90">
                      {window.location.origin}
                      {createdPublicLink}
                    </p>
                    <button
                      type="button"
                      className="mt-2 rounded-md bg-emerald-700/80 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600"
                      onClick={() => void copyPublicShareUrl(createdPublicLink)}
                    >
                      {t("dashboard:publicShareCopyLink")}
                    </button>
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap items-end gap-2">
                  <div className="min-w-[200px] flex-1">
                    <label className="mb-1 block text-[10px] text-surface-muted">
                      {t("dashboard:publicShareLabelField")}
                    </label>
                    <input
                      type="text"
                      value={publicShareLabel}
                      onChange={(e) => setPublicShareLabel(e.target.value)}
                      placeholder={t("dashboard:publicShareLabelPlaceholder")}
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-violet-500/50"
                    />
                  </div>
                  <div className="min-w-[180px]">
                    <label className="mb-1 block text-[10px] text-surface-muted">
                      {t("dashboard:publicShareExpiresLabel")}
                    </label>
                    <input
                      type="datetime-local"
                      value={publicShareExpiresAt}
                      onChange={(e) => setPublicShareExpiresAt(e.target.value)}
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-violet-500/50"
                    />
                  </div>
                  <div className="min-w-[160px]">
                    <label className="mb-1 block text-[10px] text-surface-muted">
                      {t("dashboard:publicSharePasswordField")}
                    </label>
                    <input
                      type="password"
                      value={publicSharePassword}
                      onChange={(e) => setPublicSharePassword(e.target.value)}
                      placeholder={t("dashboard:publicSharePasswordOptional")}
                      className="w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-violet-500/50"
                      autoComplete="new-password"
                    />
                  </div>
                  <button
                    type="button"
                    disabled={publicSharesBusy}
                    className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
                    onClick={() => void createPublicShare()}
                  >
                    {publicSharesBusy ? "…" : t("dashboard:publicShareCreate")}
                  </button>
                </div>
                <p className="mt-3 text-[10px] uppercase tracking-wide text-surface-muted">
                  {t("dashboard:publicShareBlocksHint")}
                </p>
                {gridLayout.blocks.length === 0 ? (
                  <p className="mt-1 text-xs text-surface-muted">{t("dashboard:noBlocksInLayoutYet")}</p>
                ) : (
                  <ul className="mt-2 max-h-48 space-y-2 overflow-y-auto rounded-lg border border-white/5 p-2 text-sm">
                    {gridLayout.blocks.map((b) => {
                      const id = typeof b.id === "string" ? b.id : String(b.id ?? "");
                      const props =
                        b.props && typeof b.props === "object" && !Array.isArray(b.props)
                          ? (b.props as { title?: string })
                          : {};
                      const label = props.title?.trim() || b.type || id;
                      if (!id) return null;
                      return (
                        <li key={`ps-${id}`} className="flex items-center gap-2">
                          <input
                            id={`pshare-${id}`}
                            type="checkbox"
                            checked={!!publicSharePick[id]}
                            onChange={(e) =>
                              setPublicSharePick((prev) => ({ ...prev, [id]: e.target.checked }))
                            }
                            className="rounded border-surface-border"
                          />
                          <label htmlFor={`pshare-${id}`} className="cursor-pointer text-neutral-200">
                            <span className="text-surface-muted">{b.type}</span> · {label}
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {publicShares.length === 0 ? (
                  <p className="mt-3 text-xs text-surface-muted">{t("dashboard:publicSharesNoneYet")}</p>
                ) : (
                  <ul className="mt-3 divide-y divide-white/5 text-sm">
                    {publicShares.map((s) => {
                      const revoked = Boolean(s.revoked_at);
                      const scopeLabel =
                        s.scope === "blocks" || s.block_ids.length > 0
                          ? t("dashboard:publicShareScopeBlocks", { count: s.block_ids.length })
                          : t("dashboard:publicShareScopeFull");
                      const expLabel =
                        s.expires_at && !revoked
                          ? t("dashboard:publicShareExpiresAt", {
                              date: new Date(s.expires_at).toLocaleString(),
                            })
                          : null;
                      return (
                        <li
                          key={s.id}
                          className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0"
                        >
                          <span className="text-neutral-200">
                            {s.label || t("dashboard:publicShareUntitled")}{" "}
                            <span className="text-surface-muted">
                              ({scopeLabel}
                              {s.password_protected ? ` · ${t("dashboard:publicSharePasswordProtected")}` : ""}
                              {expLabel ? ` · ${expLabel}` : ""}
                              {revoked ? ` · ${t("dashboard:publicShareRevoked")}` : ""})
                            </span>
                          </span>
                          {!revoked ? (
                            <button
                              type="button"
                              disabled={publicSharesBusy}
                              className="text-xs text-red-300 hover:underline disabled:opacity-50"
                              onClick={() => void revokePublicShare(s.id)}
                            >
                              {t("dashboard:publicShareRevoke")}
                            </button>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              </>
            ) : (
              <div className="rounded-xl border border-surface-border bg-black/20 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-surface-muted">
                  {t("dashboard:membersTitle")}
                </p>
                <p className="mt-2 text-sm text-surface-muted">{t("dashboard:membersManagePermissionDenied")}</p>
              </div>
            )}

            {isPrimaryOwner ? (
              <div className="rounded-xl border border-red-500/30 bg-red-950/20 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-red-200/80">
                  {t("dashboard:dangerZone")}
                </p>
                <p className="mt-2 text-xs text-red-200/80">{t("dashboard:deletePermanent")}</p>
                <button
                  type="button"
                  className="mt-3 rounded-lg border border-red-500/30 px-3 py-2 text-sm text-red-200 hover:bg-red-950/40"
                  onClick={() => void removeWs()}
                >
                  {t("dashboard:deleteDashboard")}
                </button>
              </div>
            ) : null}
          </div>
        </DashboardSettingsDrawer>
      ) : null}

      {projectsImportOpen && selectedId ? (
        <ProjectsImportModal
          open={projectsImportOpen}
          onClose={() => setProjectsImportOpen(false)}
          auth={auth}
          dashboardId={selectedId}
          onImported={(nextData) => {
            setData({ ...nextData });
            setDetail((prev) => (prev ? { ...prev, data: nextData } : prev));
            setProjectsImportOpen(false);
          }}
        />
      ) : null}

      {newWsModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
          <div
            className="absolute inset-0 bg-black/70"
            role="button"
            tabIndex={0}
            aria-label={t("dashboard:close")}
            onClick={() => setNewWsModalOpen(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setNewWsModalOpen(false);
              }
            }}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="ws-new-title"
            className="relative max-h-[85vh] w-full max-w-md overflow-y-auto rounded-xl border border-surface-border bg-surface-raised p-6 shadow-xl"
          >
            <h2 id="ws-new-title" className="text-lg font-semibold text-white">
              {t("dashboard:newDashboardModalTitle")}
            </h2>
            <p className="mt-2 text-sm text-surface-muted">{t("dashboard:newDashboardPickType")}</p>
            <ul className="mt-4 flex flex-col gap-2">
              {kindsAllowedForNewDashboard.length === 0 ? (
                <li className="text-sm text-surface-muted">{t("dashboard:installPackFromCatalogFirst")}</li>
              ) : (
                kindsAllowedForNewDashboard.map((row) => (
                  <li key={row.kind}>
                    <button
                      type="button"
                      className="w-full rounded-lg border border-surface-border px-3 py-2 text-left text-sm text-white hover:bg-white/5"
                      onClick={() => void createWs(row.kind)}
                    >
                      {row.label}
                    </button>
                  </li>
                ))
              )}
            </ul>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200 hover:bg-white/5"
                onClick={() => setNewWsModalOpen(false)}
              >
                {t("admin:cancel")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {installModalRow && schemaInstalled ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
          <div
            className="absolute inset-0 bg-black/70"
            role="button"
            tabIndex={0}
            aria-label={t("dashboard:close")}
            onClick={() => {
              if (!installBusy) setInstallModalRow(null);
            }}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && !installBusy) {
                e.preventDefault();
                setInstallModalRow(null);
              }
            }}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="ws-tpl-install-title"
            className="relative w-full max-w-md rounded-xl border border-surface-border bg-surface-raised p-6 shadow-xl"
          >
            <h2 id="ws-tpl-install-title" className="text-lg font-semibold text-white">
              {t("dashboard:installPackConfirmTitle", { label: installModalRow.label })}
            </h2>
            {installModalRow.description ? (
              <p className="mt-2 text-sm text-surface-muted">{installModalRow.description}</p>
            ) : null}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={installBusy}
                className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-50"
                onClick={() => setInstallModalRow(null)}
              >
                {t("admin:cancel")}
              </button>
              <button
                type="button"
                disabled={installBusy || !installModalRow.has_schema}
                className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                onClick={() => void runInstallTemplates(installModalRow.kind)}
              >
                {installBusy ? t("dashboard:installing") : t("dashboard:install")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {pinModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div
            role="dialog"
            aria-modal="true"
            className="w-full max-w-md rounded-xl border border-surface-border bg-surface-raised p-6 shadow-xl"
          >
            <h2 className="text-lg font-semibold text-white">{t("dashboard:pinBlockTitle")}</h2>
            <label className="mt-4 block text-sm text-surface-muted">
              {t("dashboard:pinBlockTarget")}
              <select
                value={pinTargetId}
                onChange={(e) => setPinTargetId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-surface-border bg-black/30 px-3 py-2 text-sm text-white"
              >
                {pinTargetOptions.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.title || w.kind}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-surface-border px-4 py-2 text-sm text-neutral-200"
                onClick={() => setPinModalOpen(false)}
              >
                {t("admin:cancel")}
              </button>
              <button
                type="button"
                disabled={pinBusy || !pinTargetId}
                className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
                onClick={() => void confirmPinBlock()}
              >
                {pinBusy ? "…" : t("dashboard:pinBlockConfirm")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
