import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { useTranslation } from "react-i18next";

type ShareItem = {
  resource_type: string;
  grantee_user_id?: string;
  owner_user_id?: string;
  email: string;
  display_name: string;
  created_at: string;
};

type FriendShares = {
  outgoing: string[];
  incoming: string[];
};

const RESOURCE_TYPES = [
  { id: 'google_calendar', name: 'Google Calendar', icon: '📅' },
  { id: 'github_activity', name: 'GitHub Activity', icon: '🐙' },
  { id: 'todoist', name: 'Todoist', icon: '✅' },
  { id: 'notes', name: 'Notes', icon: '📝' },
  { id: 'roadmap', name: 'Project Roadmap', icon: '🗺️' },
];

export default function SharesSettings() {
  const { t } = useTranslation(["settings"]);
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [outgoing, setOutgoing] = useState<ShareItem[]>([]);
  const [incoming, setIncoming] = useState<ShareItem[]>([]);
  const [activeTab, setActiveTab] = useState<"outgoing" | "incoming">("outgoing");
  const [selectedFriend, setSelectedFriend] = useState<ShareItem | null>(null);
  const [friendShares, setFriendShares] = useState<FriendShares | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [outgoingRes, incomingRes, friendsRes] = await Promise.all([
        apiFetch("/v1/shares/outgoing", auth),
        apiFetch("/v1/shares/incoming", auth),
        apiFetch("/v1/friends", auth)
      ]);

      if (outgoingRes.ok) {
        const data = await outgoingRes.json();
        setOutgoing(data.shares || []);
      }
      if (incomingRes.ok) {
        const data = await incomingRes.json();
        setIncoming(data.shares || []);
      }
      
      // Add all confirmed friends even if no shares yet
      if (friendsRes.ok) {
        const friendsData = await friendsRes.json();
        const confirmedFriends = friendsData.friends || [];
        
        // Merge friends with existing shares
        const existingUserIds = new Set(outgoing.map(s => s.grantee_user_id));
        
        for (const friend of confirmedFriends) {
          if (!existingUserIds.has(friend.friend_user_id)) {
            // Add friend with empty shares
            outgoing.push({
              resource_type: '',
              grantee_user_id: friend.friend_user_id,
              email: friend.email,
              display_name: friend.display_name,
              created_at: friend.created_at
            });
          }
        }
        
        setOutgoing([...outgoing]);
      }
      
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:sharesLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  async function loadFriendShares(friend: ShareItem) {
    setSelectedFriend(friend);
    try {
      const res = await apiFetch(`/v1/shares/friend/${friend.grantee_user_id || friend.owner_user_id}`, auth);
      if (res.ok) {
        const data = await res.json();
        setFriendShares(data);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:friendSharesLoadFailed"));
    }
  }

  async function toggleShare(resourceType: string, isAllowed: boolean) {
    if (!selectedFriend || saving) return;
    
    setSaving(true);
    try {
      await apiFetch("/v1/shares/set", auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          grantee_user_id: selectedFriend.grantee_user_id,
          resource_type: resourceType,
          resource_identifier: "primary",
          is_allowed: isAllowed
        }),
      });
      
      await load();
      await loadFriendShares(selectedFriend);
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:shareUpdateFailed"));
    } finally {
      setSaving(false);
    }
  }

  function groupByUser(shares: ShareItem[]) {
    const groups: Record<string, ShareItem[]> = {};
    for (const share of shares) {
      const userId = share.grantee_user_id || share.owner_user_id || '';
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
        <p className="mt-2 text-sm text-surface-muted">
          {t("settings:sharesSubtitle")}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-surface-border pb-1">
        <button
          type="button"
          onClick={() => { setActiveTab("outgoing"); setSelectedFriend(null); }}
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
          onClick={() => { setActiveTab("incoming"); setSelectedFriend(null); }}
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
            return (
              <div 
                key={userId} 
                className="rounded-xl border border-surface-border bg-surface-raised p-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  loadFriendShares(friend);
                }}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">{friend.display_name || friend.email}</div>
                    <div className="text-sm text-neutral-400 mt-1">
                      {shares.map(s => RESOURCE_TYPES.find(r => r.id === s.resource_type)?.name).filter(Boolean).join(', ')}
                    </div>
                  </div>
                  <div className="text-sm text-surface-muted">
                    {t("settings:sharesResourcesCount", { count: shares.length })}
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
            return (
              <div 
                key={userId} 
                className="rounded-xl border border-surface-border bg-surface-raised p-4"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">{friend.display_name || friend.email}</div>
                    <div className="text-sm text-neutral-400 mt-1">
                      {shares.map(s => RESOURCE_TYPES.find(r => r.id === s.resource_type)?.name).filter(Boolean).join(', ')}
                    </div>
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
            <p className="text-sm text-surface-muted mt-1">
              {t("settings:sharesManageFriend")}
            </p>
          </div>

          <div className="p-4 space-y-6">
            <div>
              <h4 className="text-sm font-medium mb-4 text-white">{t("settings:sharesWhatYouShare")}</h4>
              <div className="space-y-3">
                {RESOURCE_TYPES.map(resource => (
                  <div key={resource.id} className="flex items-center justify-between py-2">
                    <div className="flex items-center gap-3">
                      <div className="text-xl">{resource.icon}</div>
                      <span className="text-white">{resource.name}</span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={friendShares.outgoing.includes(resource.id)}
                        onChange={(e) => toggleShare(resource.id, e.target.checked)}
                        disabled={saving}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-neutral-700 peer-checked:bg-emerald-600 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all"></div>
                    </label>
                  </div>
                ))}
              </div>
            </div>

            <div className="border-t border-surface-border pt-6">
              <h4 className="text-sm font-medium mb-4 text-white">{t("settings:sharesWhatTheyShare")}</h4>
              <div className="space-y-3">
                {RESOURCE_TYPES.map(resource => (
                  <div key={`in-${resource.id}`} className="flex items-center justify-between py-2">
                    <div className="flex items-center gap-3">
                      <div className="text-xl">{resource.icon}</div>
                      <span className="text-white">{resource.name}</span>
                    </div>
                    <div className="text-sm">
                      {friendShares.incoming.includes(resource.id) ? (
                        <span className="text-emerald-400 font-medium">{t("settings:sharesAccessGranted")}</span>
                      ) : (
                        <span className="text-surface-muted">{t("settings:sharesNotShared")}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}