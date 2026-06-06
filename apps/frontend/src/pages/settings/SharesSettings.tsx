import { useCallback, useEffect, useState } from "react";
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

type CatalogResource = {
  id: string;
  name: string;
  icon: string;
  default_identifier: string;
  policy_fields: string[];
};

function grantForResource(
  grants: ShareGrant[] | undefined,
  resourceId: string,
): ShareGrant | undefined {
  return grants?.find((g) => g.resource_type === resourceId);
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

  const lang = (i18n.language || "en").slice(0, 2);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [catalogRes, outgoingRes, incomingRes, friendsRes] = await Promise.all([
        apiFetch(`/v1/shares/catalog?lang=${lang}`, auth),
        apiFetch("/v1/shares/outgoing", auth),
        apiFetch("/v1/shares/incoming", auth),
        apiFetch("/v1/friends", auth),
      ]);

      if (catalogRes.ok) {
        const data = await catalogRes.json();
        setCatalog(data.resources || []);
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
          resource_identifier: "primary",
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

  function catalogName(resourceId: string): string {
    return catalog.find((r) => r.id === resourceId)?.name || resourceId;
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

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-lg font-semibold text-white">🔗 {t("settings:sharesTitle")}</h1>
        <p className="mt-2 text-sm text-surface-muted">{t("settings:sharesSubtitle")}</p>
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
              ? "text-white border-b-2 border-sky-500"
              : "text-surface-muted hover:text-white"
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
              ? "text-white border-b-2 border-sky-500"
              : "text-surface-muted hover:text-white"
          }`}
        >
          {t("settings:sharesTabIncoming")}
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-surface-muted">{t("settings:sharesLoading")}</p>
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
                className="rounded-xl border border-surface-border bg-surface-raised p-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  void loadFriendShares(friend);
                }}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">{friend.display_name || friend.email}</div>
                    <div className="text-sm text-neutral-400 mt-1">{resourceNames.join(", ")}</div>
                  </div>
                  <div className="text-sm text-surface-muted">
                    {t("settings:sharesResourcesCount", {
                      count: shares.filter((s) => s.resource_type).length,
                    })}
                  </div>
                </div>
              </div>
            );
          })}

          {Object.keys(groupByUser(outgoing)).length === 0 && (
            <div className="p-8 text-center text-surface-muted rounded-xl border border-surface-border bg-surface-raised">
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
                className="rounded-xl border border-surface-border bg-surface-raised p-4"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">{friend.display_name || friend.email}</div>
                    <div className="text-sm text-neutral-400 mt-1">{resourceNames.join(", ")}</div>
                  </div>
                  <div className="text-sm text-surface-muted">
                    {t("settings:sharesResourcesCount", { count: shares.length })}
                  </div>
                </div>
              </div>
            );
          })}

          {Object.keys(groupByUser(incoming)).length === 0 && (
            <div className="p-8 text-center text-surface-muted rounded-xl border border-surface-border bg-surface-raised">
              {t("settings:sharesNoneIncoming")}
            </div>
          )}
        </div>
      )}

      {selectedFriend && friendShares && (
        <div className="rounded-xl border border-surface-border bg-surface-raised overflow-hidden mt-8">
          <div className="p-4 border-b border-surface-border">
            <h3 className="font-medium text-white">
              {selectedFriend.display_name || selectedFriend.email}
            </h3>
            <p className="text-sm text-surface-muted mt-1">{t("settings:sharesManageFriend")}</p>
          </div>

          <div className="p-4 space-y-6">
            <div>
              <h4 className="text-sm font-medium mb-4 text-white">{t("settings:sharesWhatYouShare")}</h4>
              <div className="space-y-4">
                {catalog.map((resource) => {
                  const enabled = friendShares.outgoing.includes(resource.id);
                  const grant = grantForResource(friendShares.outgoing_grants, resource.id);
                  const draft = policyDraft[resource.id] || grant?.policy || {};
                  const showDays = resource.policy_fields.includes("days_ahead");
                  const showExpiry = resource.policy_fields.includes("expires_at");

                  return (
                    <div
                      key={resource.id}
                      className="rounded-lg border border-surface-border/60 p-3 space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="text-xl">{resource.icon}</div>
                          <span className="text-white">{resource.name}</span>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) => void toggleShare(resource.id, e.target.checked)}
                            disabled={saving}
                            className="sr-only peer"
                          />
                          <div className="w-9 h-5 bg-neutral-700 peer-checked:bg-emerald-600 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all" />
                        </label>
                      </div>

                      {enabled && (showDays || showExpiry) && (
                        <div className="grid gap-3 sm:grid-cols-2 pl-1">
                          {showDays && (
                            <label className="block text-sm">
                              <span className="text-surface-muted">{t("settings:sharesDaysAhead")}</span>
                              <input
                                type="number"
                                min={1}
                                max={366}
                                value={draft.days_ahead ?? ""}
                                placeholder={t("settings:sharesDaysAheadPlaceholder")}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setPolicyDraft((prev) => ({
                                    ...prev,
                                    [resource.id]: {
                                      ...prev[resource.id],
                                      days_ahead: val ? Number(val) : undefined,
                                    },
                                  }));
                                }}
                                className="mt-1 w-full rounded-md border border-surface-border bg-surface px-2 py-1.5 text-white text-sm"
                              />
                            </label>
                          )}
                          {showExpiry && (
                            <label className="block text-sm">
                              <span className="text-surface-muted">{t("settings:sharesExpiresAt")}</span>
                              <input
                                type="datetime-local"
                                value={
                                  draft.expires_at
                                    ? draft.expires_at.slice(0, 16)
                                    : ""
                                }
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setPolicyDraft((prev) => ({
                                    ...prev,
                                    [resource.id]: {
                                      ...prev[resource.id],
                                      expires_at: val ? new Date(val).toISOString() : undefined,
                                    },
                                  }));
                                }}
                                className="mt-1 w-full rounded-md border border-surface-border bg-surface px-2 py-1.5 text-white text-sm"
                              />
                            </label>
                          )}
                          <div className="sm:col-span-2">
                            <button
                              type="button"
                              disabled={saving}
                              onClick={() => void savePolicy(resource.id)}
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
              </div>
            </div>

            <div className="border-t border-surface-border pt-6">
              <h4 className="text-sm font-medium mb-4 text-white">{t("settings:sharesWhatTheyShare")}</h4>
              <div className="space-y-3">
                {catalog.map((resource) => {
                  const grant = grantForResource(friendShares.incoming_grants, resource.id);
                  const enabled = friendShares.incoming.includes(resource.id);
                  return (
                    <div
                      key={`in-${resource.id}`}
                      className="flex items-center justify-between py-2"
                    >
                      <div className="flex items-center gap-3">
                        <div className="text-xl">{resource.icon}</div>
                        <div>
                          <span className="text-white">{resource.name}</span>
                          {enabled && grant?.policy?.days_ahead && (
                            <div className="text-xs text-surface-muted">
                              {t("settings:sharesDaysAheadValue", { count: grant.policy.days_ahead })}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="text-sm">
                        {enabled ? (
                          <span className="text-emerald-400 font-medium">
                            {t("settings:sharesAccessGranted")}
                          </span>
                        ) : (
                          <span className="text-surface-muted">{t("settings:sharesNotShared")}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
