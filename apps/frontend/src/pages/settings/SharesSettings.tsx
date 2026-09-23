import { useCallback, useEffect, useState } from "react";
import { Link as LinkIcon } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { useTranslation } from "react-i18next";

type ShareItem = {
  resource_type: string;
  resource_identifier?: string;
  policy?: SharePolicy;
  grantee_user_id?: string;
  owner_user_id?: string;
  email: string;
  display_name: string;
  created_at: string;
};

type SharePolicy = {
  days_ahead?: number;
  expires_at?: string;
  permission?: string;
  block_ids?: string[];
};

type ShareGrant = {
  resource_type: string;
  resource_identifier?: string;
  policy?: SharePolicy;
};

type FriendShares = {
  outgoing: string[];
  incoming: string[];
  outgoing_grants?: ShareGrant[];
  incoming_grants?: ShareGrant[];
};

/**
 * One shareable resource type, as described by the backend adapter registry.
 *
 * The shape is the registry's, not a hand-maintained list: `policy_fields` is
 * what that type's adapter actually reads, so the editor below renders exactly
 * those inputs and never offers a value the grant path would reject.
 * `default_identifier` is null when the type needs an explicit identifier
 * (a collection slug, a dashboard uuid) rather than a usable default.
 */
type CatalogResource = {
  id: string;
  name: string;
  default_identifier: string | null;
  policy_fields: string[];
  listable: boolean;
  aliases: string[];
  previewable?: boolean;
};

/**
 * One view the caller has published of their own resource.
 *
 * Keyed on (resource_type, resource_identifier) and never on a friend.
 * That is the model, not a simplification: there is one row per resource,
 * so the shape chosen here is what every grantee of that resource sees.
 */
type PublishedProjection = {
  resource_type: string;
  resource_identifier: string;
  projection_kind: string | null;
  available_kinds: string[];
  default_kind: string | null;
  generated_at: string | null;
  expires_at: string | null;
  fresh: boolean;
};

const projectionKey = (resourceType: string, identifier: string) =>
  `${resourceType}:${identifier}`;

function grantForResource(
  grants: ShareGrant[] | undefined,
  resourceId: string,
): ShareGrant | undefined {
  return grants?.find((g) => g.resource_type === resourceId);
}

/**
 * Find the catalog entry for a resource id, following legacy aliases.
 *
 * A grant stored years ago under "calendar" must still find the
 * google_calendar entry, or it would render with no policy fields and the
 * user could not edit a share that is really a calendar share.
 */
function catalogEntry(
  resourceId: string,
  catalog: CatalogResource[],
): CatalogResource | undefined {
  return catalog.find((r) => r.id === resourceId || (r.aliases || []).includes(resourceId));
}

function resourceTypesForFriend(friendShares: FriendShares): string[] {
  const ids = new Set<string>();
  for (const id of friendShares.outgoing) {
    if (id) ids.add(id);
  }
  for (const id of friendShares.incoming) {
    if (id) ids.add(id);
  }
  for (const g of friendShares.outgoing_grants || []) {
    if (g.resource_type) ids.add(g.resource_type);
  }
  for (const g of friendShares.incoming_grants || []) {
    if (g.resource_type) ids.add(g.resource_type);
  }
  return Array.from(ids).sort();
}

function displayResourceName(resourceId: string, catalog: CatalogResource[]): string {
  return catalogEntry(resourceId, catalog)?.name || resourceId.replace(/_/g, " ");
}

export default function SharesSettings() {
  const { t, i18n } = useTranslation(["settings"]);
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [catalog, setCatalog] = useState<CatalogResource[]>([]);
  const [outgoing, setOutgoing] = useState<ShareItem[]>([]);
  const [incoming, setIncoming] = useState<ShareItem[]>([]);
  const [activeTab, setActiveTab] = useState<"outgoing" | "incoming">("outgoing");
  const [selectedFriend, setSelectedFriend] = useState<ShareItem | null>(null);
  const [friendShares, setFriendShares] = useState<FriendShares | null>(null);
  const [policyDraft, setPolicyDraft] = useState<Record<string, SharePolicy>>({});
  const [newResourceType, setNewResourceType] = useState("");
  const [newResourceIdentifier, setNewResourceIdentifier] = useState("");
  const [myProjections, setMyProjections] = useState<PublishedProjection[]>([]);
  const [kindDraft, setKindDraft] = useState<Record<string, string>>({});
  const [publishing, setPublishing] = useState(false);

  const lang = (i18n.language || "en").slice(0, 2);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [catalogRes, outgoingRes, incomingRes, friendsRes, projectionRes] =
        await Promise.all([
          apiFetch(`/v1/shares/catalog?lang=${lang}`, auth),
          apiFetch("/v1/shares/outgoing", auth),
          apiFetch("/v1/shares/incoming", auth),
          apiFetch("/v1/friends", auth),
          apiFetch("/v1/shares/projections", auth),
        ]);

      if (catalogRes.ok) {
        const data = await catalogRes.json();
        setCatalog(data.resources || []);
      }

      if (projectionRes.ok) {
        const data = await projectionRes.json();
        const rows: PublishedProjection[] = data.projections || [];
        setMyProjections(rows);
        const drafts: Record<string, string> = {};
        for (const row of rows) {
          drafts[projectionKey(row.resource_type, row.resource_identifier)] =
            row.projection_kind || row.default_kind || "";
        }
        setKindDraft(drafts);
      }

      let outgoingRows: ShareItem[] = [];
      if (outgoingRes.ok) {
        const data = await outgoingRes.json();
        outgoingRows = data.shares || [];
      }
      if (incomingRes.ok) {
        const data = await incomingRes.json();
        setIncoming(data.shares || []);
      }

      if (friendsRes.ok) {
        const friendsData = await friendsRes.json();
        const confirmedFriends = friendsData.friends || [];
        const existingUserIds = new Set(outgoingRows.map((s) => s.grantee_user_id));

        for (const friend of confirmedFriends) {
          if (!existingUserIds.has(friend.friend_user_id)) {
            outgoingRows.push({
              resource_type: "",
              grantee_user_id: friend.friend_user_id,
              email: friend.email,
              display_name: friend.display_name,
              created_at: friend.created_at,
            });
          }
        }
      }

      setOutgoing(outgoingRows);
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:sharesLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [auth, lang, t]);

  async function loadFriendShares(friend: ShareItem) {
    setSelectedFriend(friend);
    try {
      const res = await apiFetch(
        `/v1/shares/friend/${friend.grantee_user_id || friend.owner_user_id}`,
        auth,
      );
      if (res.ok) {
        const data = (await res.json()) as FriendShares;
        setFriendShares(data);
        const draft: Record<string, SharePolicy> = {};
        for (const g of data.outgoing_grants || []) {
          draft[g.resource_type] = { ...(g.policy || {}) };
        }
        setPolicyDraft(draft);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:friendSharesLoadFailed"));
    }
  }

  async function setShare(
    resourceType: string,
    isAllowed: boolean,
    policy?: SharePolicy,
    identifier?: string,
  ) {
    if (!selectedFriend || saving) return;

    setSaving(true);
    setErr(null);
    try {
      const res = await apiFetch("/v1/shares/set", auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          grantee_user_id: selectedFriend.grantee_user_id,
          resource_type: resourceType,
          // Derived from the adapter rather than hardcoded: a calendar share is
          // one-per-user and defaults to "primary", a collection needs its
          // slug and a dashboard its uuid. The caller supplies those when the
          // type has no usable default.
          resource_identifier:
            identifier ??
            catalogEntry(resourceType, catalog)?.default_identifier ??
            "primary",
          is_allowed: isAllowed,
          policy: isAllowed ? policy || {} : undefined,
        }),
      });
      if (!res.ok) {
        setErr(await res.text());
        return;
      }

      await load();
      await loadFriendShares(selectedFriend);
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:shareUpdateFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function toggleShare(resourceType: string, isAllowed: boolean) {
    const policy = policyDraft[resourceType] || {};
    await setShare(resourceType, isAllowed, policy);
  }

  async function savePolicy(resourceType: string) {
    if (!friendShares?.outgoing.includes(resourceType)) return;
    await setShare(resourceType, true, policyDraft[resourceType] || {});
  }

  /**
   * Republish one of the caller's own resources in a different shape.
   *
   * Separate from setShare on purpose: this changes what the view *is*,
   * not who may read it. Publishing grants nothing, and a view nobody has
   * been granted stays unreadable.
   */
  async function publishKind(row: PublishedProjection) {
    const key = projectionKey(row.resource_type, row.resource_identifier);
    const kind = kindDraft[key];
    if (!kind || publishing) return;

    setPublishing(true);
    setErr(null);
    try {
      const res = await apiFetch("/v1/shares/projection", auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resource_type: row.resource_type,
          resource_identifier: row.resource_identifier,
          projection_kind: kind,
        }),
      });
      if (!res.ok) {
        setErr(await res.text());
        return;
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:sharesPublishFailed"));
    } finally {
      setPublishing(false);
    }
  }

  function catalogName(resourceId: string): string {
    return displayResourceName(resourceId, catalog);
  }

  function updateDraft(resourceId: string, patch: SharePolicy) {
    setPolicyDraft((prev) => ({
      ...prev,
      [resourceId]: { ...prev[resourceId], ...patch },
    }));
  }

  /**
   * Editor for a single policy field, chosen by the adapter's declared
   * `policy_fields` rather than rendered unconditionally.
   *
   * Before this the editor showed days_ahead and expires_at for every type,
   * so a user could set days_ahead on a dashboard share — a field the
   * dashboard adapter does not read and the backend rejects at grant time.
   * Rendering only what the adapter honours removes that class of dead input.
   */
  function renderPolicyField(field: string, resourceId: string, draft: SharePolicy) {
    const cls =
      "mt-1 w-full rounded-md border border-surface-border bg-canvas px-2 py-1.5 text-ink-primary text-sm";
    switch (field) {
      case "days_ahead":
        return (
          <label className="block text-sm">
            <span className="text-ink-muted">{t("settings:sharesDaysAhead")}</span>
            <input
              type="number"
              min={1}
              max={366}
              value={draft.days_ahead ?? ""}
              placeholder={t("settings:sharesDaysAheadPlaceholder")}
              onChange={(e) => {
                const val = e.target.value;
                updateDraft(resourceId, { days_ahead: val ? Number(val) : undefined });
              }}
              className={cls}
            />
          </label>
        );
      case "expires_at":
        return (
          <label className="block text-sm">
            <span className="text-ink-muted">{t("settings:sharesExpiresAt")}</span>
            <input
              type="datetime-local"
              value={draft.expires_at ? draft.expires_at.slice(0, 16) : ""}
              onChange={(e) => {
                const val = e.target.value;
                updateDraft(resourceId, {
                  expires_at: val ? new Date(val).toISOString() : undefined,
                });
              }}
              className={cls}
            />
          </label>
        );
      case "permission":
        return (
          <label className="block text-sm">
            <span className="text-ink-muted">{t("settings:sharesPermission")}</span>
            <select
              value={draft.permission ?? "view"}
              onChange={(e) => updateDraft(resourceId, { permission: e.target.value })}
              className={cls}
            >
              <option value="view">{t("settings:sharesPermissionView")}</option>
              <option value="edit">{t("settings:sharesPermissionEdit")}</option>
            </select>
          </label>
        );
      case "block_ids":
        return (
          <label className="block text-sm">
            <span className="text-ink-muted">{t("settings:sharesBlockIds")}</span>
            <input
              type="text"
              value={(draft.block_ids || []).join(", ")}
              placeholder={t("settings:sharesBlockIdsPlaceholder")}
              onChange={(e) =>
                updateDraft(resourceId, {
                  block_ids: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              className={cls}
            />
          </label>
        );
      default:
        return null;
    }
  }

  function groupByUser(shares: ShareItem[]) {
    const groups: Record<string, ShareItem[]> = {};
    for (const share of shares) {
      const userId = share.grantee_user_id || share.owner_user_id || "";
      if (!groups[userId]) groups[userId] = [];
      groups[userId].push(share);
    }
    return groups;
  }

  useEffect(() => {
    void load();
  }, [load]);

  // A type whose adapter has no usable default identifier (a collection needs
  // a slug, a dashboard a uuid) must be given one explicitly before it can
  // be shared.
  const selectedNewType = catalogEntry(newResourceType, catalog);
  const needsIdentifier =
    !!selectedNewType && selectedNewType.default_identifier === null;
  const canAddResource =
    !!newResourceType && (!needsIdentifier || !!newResourceIdentifier.trim());

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-semibold text-ink-primary">
          <LinkIcon aria-hidden className="h-5 w-5" />
          {t("settings:sharesTitle")}
        </h1>
        <p className="mt-2 text-sm text-ink-muted">{t("settings:sharesSubtitle")}</p>
      </div>

      <div className="flex gap-4 border-b border-surface-border pb-1">
        <button
          type="button"
          onClick={() => {
            setActiveTab("outgoing");
            setSelectedFriend(null);
          }}
          className={`px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === "outgoing"
              ? "text-ink-primary border-b-2 border-sky-500"
              : "text-ink-muted hover:text-white"
          }`}
        >
          {t("settings:sharesTabOutgoing")}
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab("incoming");
            setSelectedFriend(null);
          }}
          className={`px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === "incoming"
              ? "text-ink-primary border-b-2 border-sky-500"
              : "text-ink-muted hover:text-white"
          }`}
        >
          {t("settings:sharesTabIncoming")}
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-ink-muted">{t("settings:sharesLoading")}</p>
      ) : err ? (
        <p className="text-sm text-amber-400">{err}</p>
      ) : activeTab === "outgoing" ? (
        <div className="space-y-6">
          {Object.entries(groupByUser(outgoing)).map(([userId, shares]) => {
            const friend = shares[0];
            const resourceNames = shares
              .map((s) => (s.resource_type ? catalogName(s.resource_type) : null))
              .filter(Boolean);
            return (
              <div
                key={userId}
                className="rounded-xl border border-surface-border bg-card p-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  void loadFriendShares(friend);
                }}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-ink-primary">{friend.display_name || friend.email}</div>
                    <div className="text-sm text-ink-muted mt-1">{resourceNames.join(", ")}</div>
                  </div>
                  <div className="text-sm text-ink-muted">
                    {t("settings:sharesResourcesCount", {
                      count: shares.filter((s) => s.resource_type).length,
                    })}
                  </div>
                </div>
              </div>
            );
          })}

          {Object.keys(groupByUser(outgoing)).length === 0 && (
            <div className="p-8 text-center text-ink-muted rounded-xl border border-surface-border bg-card">
              {t("settings:sharesNoneOutgoing")}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(groupByUser(incoming)).map(([userId, shares]) => {
            const friend = shares[0];
            const resourceNames = shares
              .map((s) => catalogName(s.resource_type))
              .filter(Boolean);
            return (
              <div
                key={userId}
                className="rounded-xl border border-surface-border bg-card p-4"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-ink-primary">{friend.display_name || friend.email}</div>
                    <div className="text-sm text-ink-muted mt-1">{resourceNames.join(", ")}</div>
                  </div>
                  <div className="text-sm text-ink-muted">
                    {t("settings:sharesResourcesCount", { count: shares.length })}
                  </div>
                </div>
              </div>
            );
          })}

          {Object.keys(groupByUser(incoming)).length === 0 && (
            <div className="p-8 text-center text-ink-muted rounded-xl border border-surface-border bg-card">
              {t("settings:sharesNoneIncoming")}
            </div>
          )}
        </div>
      )}

      {!loading && (
        <div className="rounded-xl border border-surface-border bg-card p-4">
          <h3 className="font-medium text-ink-primary">
            {t("settings:sharesPublishedTitle")}
          </h3>
          <p className="mt-1 text-sm text-ink-muted">
            {t("settings:sharesPublishedHint")}
          </p>

          {myProjections.length === 0 ? (
            <p className="mt-4 text-sm text-ink-muted">
              {t("settings:sharesPublishedNone")}
            </p>
          ) : (
            <div className="mt-4 space-y-3">
              {myProjections.map((row) => {
                const key = projectionKey(row.resource_type, row.resource_identifier);
                const draft = kindDraft[key] ?? row.projection_kind ?? "";
                const unchanged = draft === row.projection_kind;
                return (
                  <div
                    key={key}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border/60 p-3"
                  >
                    <div className="min-w-[10rem]">
                      <div className="text-ink-primary">
                        {displayResourceName(row.resource_type, catalog)}
                      </div>
                      <div className="mt-0.5 text-xs text-ink-muted">
                        {t("settings:sharesPublishedIdentifier", {
                          value: row.resource_identifier,
                        })}{" "}
                        ·{" "}
                        <span className={row.fresh ? "text-emerald-400" : "text-amber-400"}>
                          {row.fresh
                            ? t("settings:sharesPublishedFresh")
                            : t("settings:sharesPublishedStale")}
                        </span>
                      </div>
                    </div>
                    {row.available_kinds.length > 0 ? (
                      <div className="flex items-center gap-2">
                        <select
                          value={draft}
                          disabled={publishing}
                          aria-label={t("settings:sharesPublishedKind", {
                            value: displayResourceName(row.resource_type, catalog),
                          })}
                          onChange={(e) =>
                            setKindDraft((prev) => ({ ...prev, [key]: e.target.value }))
                          }
                          className="rounded-md border border-surface-border bg-field px-2 py-1.5 text-sm text-ink-primary"
                        >
                          {row.available_kinds.map((kind) => (
                            <option key={kind} value={kind}>
                              {kind}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          disabled={publishing || unchanged || !draft}
                          onClick={() => void publishKind(row)}
                          className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm text-ink-on-fill disabled:opacity-50"
                        >
                          {t("settings:sharesPublishButton")}
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-ink-muted">
                        {row.projection_kind}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {selectedFriend && friendShares && (
        <div className="rounded-xl border border-surface-border bg-card overflow-hidden mt-8">
          <div className="p-4 border-b border-surface-border">
            <h3 className="font-medium text-ink-primary">
              {selectedFriend.display_name || selectedFriend.email}
            </h3>
            <p className="text-sm text-ink-muted mt-1">{t("settings:sharesManageFriend")}</p>
          </div>

          <div className="p-4 space-y-6">
            <div>
              <h4 className="text-sm font-medium mb-4 text-ink-primary">{t("settings:sharesWhatYouShare")}</h4>
              <div className="space-y-4">
                {resourceTypesForFriend(friendShares).map((resourceId) => {
                  const enabled = friendShares.outgoing.includes(resourceId);
                  const grant = grantForResource(friendShares.outgoing_grants, resourceId);
                  const draft = policyDraft[resourceId] || grant?.policy || {};

                  return (
                    <div
                      key={resourceId}
                      className="rounded-lg border border-surface-border/60 p-3 space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-ink-primary">{displayResourceName(resourceId, catalog)}</span>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) => void toggleShare(resourceId, e.target.checked)}
                            disabled={saving}
                            className="sr-only peer"
                          />
                          <div className="w-9 h-5 bg-neutral-700 peer-checked:bg-emerald-600 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all" />
                        </label>
                      </div>

                      {enabled && (
                        <div className="grid gap-3 sm:grid-cols-2 pl-1">
                          {(catalogEntry(resourceId, catalog)?.policy_fields || []).map(
                            (field) => (
                              <div
                                key={field}
                                className={field === "block_ids" ? "sm:col-span-2" : ""}
                              >
                                {renderPolicyField(field, resourceId, draft)}
                              </div>
                            ),
                          )}
                          <div className="sm:col-span-2">
                            <button
                              type="button"
                              disabled={saving}
                              onClick={() => void savePolicy(resourceId)}
                              className="text-sm text-sky-400 hover:text-sky-300 disabled:opacity-50"
                            >
                              {t("settings:sharesSavePolicy")}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
                <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-surface-border/60">
                  <label className="block text-sm flex-1 min-w-[12rem]">
                    <span className="text-ink-muted">
                      {t("settings:sharesSelectResourceType")}
                    </span>
                    <select
                      value={newResourceType}
                      onChange={(e) => setNewResourceType(e.target.value)}
                      className="mt-1 w-full rounded-md border border-surface-border bg-field px-2 py-1.5 text-ink-primary text-sm"
                    >
                      <option value="" disabled>
                        {t("settings:sharesSelectTypePlaceholder")}
                      </option>
                      {catalog.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {needsIdentifier && (
                    <label className="block text-sm flex-1 min-w-[12rem]">
                      <span className="text-ink-muted">
                        {t("settings:sharesIdentifier")}
                      </span>
                      <input
                        type="text"
                        value={newResourceIdentifier}
                        placeholder={t("settings:sharesIdentifierPlaceholder")}
                        onChange={(e) => setNewResourceIdentifier(e.target.value)}
                        className="mt-1 w-full rounded-md border border-surface-border bg-field px-2 py-1.5 text-ink-primary text-sm"
                      />
                    </label>
                  )}
                  <button
                    type="button"
                    disabled={saving || !canAddResource}
                    onClick={() => {
                      void setShare(
                        newResourceType,
                        true,
                        policyDraft[newResourceType] || {},
                        needsIdentifier ? newResourceIdentifier.trim() : undefined,
                      );
                      setNewResourceType("");
                      setNewResourceIdentifier("");
                    }}
                    className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm text-ink-on-fill disabled:opacity-50"
                  >
                    {t("settings:sharesAddResource")}
                  </button>
                  {catalog.length === 0 && (
                    <p className="w-full text-sm text-ink-muted">
                      {t("settings:sharesNoTypesRegistered")}
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="border-t border-surface-border pt-6">
              <h4 className="text-sm font-medium mb-4 text-ink-primary">{t("settings:sharesWhatTheyShare")}</h4>
              <div className="space-y-3">
                {resourceTypesForFriend(friendShares).map((resourceId) => {
                  const grant = grantForResource(friendShares.incoming_grants, resourceId);
                  const enabled = friendShares.incoming.includes(resourceId);
                  return (
                    <div
                      key={`in-${resourceId}`}
                      className="flex items-center justify-between py-2"
                    >
                      <div>
                        <span className="text-ink-primary">{displayResourceName(resourceId, catalog)}</span>
                        {enabled && grant?.policy?.days_ahead && (
                          <div className="text-xs text-ink-muted">
                            {t("settings:sharesDaysAheadValue", { count: grant.policy.days_ahead })}
                          </div>
                        )}
                      </div>
                      <div className="text-sm">
                        {enabled ? (
                          <span className="text-emerald-400 font-medium">
                            {t("settings:sharesAccessGranted")}
                          </span>
                        ) : (
                          <span className="text-ink-muted">{t("settings:sharesNotShared")}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
                {resourceTypesForFriend(friendShares).length === 0 && (
                  <p className="text-sm text-ink-muted">{t("settings:sharesNotShared")}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
