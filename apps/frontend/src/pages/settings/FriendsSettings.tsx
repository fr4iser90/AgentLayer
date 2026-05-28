import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";

type FriendRequest = {
  id: number;
  from_user_id: string;
  email: string;
  display_name: string;
  message: string | null;
  created_at: string;
};

type ConfirmedFriend = {
  id: number;
  friend_user_id: string;
  email: string;
  display_name: string;
  relation: string | null;
  note: string | null;
  created_at: string;
  discord_user_id: string | null;
};

type KnownPerson = {
  name: string;
  nickname?: string;
  email?: string;
  relation?: string;
  description?: string;
  tone?: string;
  birthday?: string;
  discord_user_id?: string;
  notes?: string;
};

export function FriendsSettings() {
  const { t } = useTranslation(["settings"]);
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [incomingRequests, setIncomingRequests] = useState<FriendRequest[]>([]);
  const [outgoingRequests, setOutgoingRequests] = useState<FriendRequest[]>([]);
  const [confirmedFriends, setConfirmedFriends] = useState<ConfirmedFriend[]>([]);
  const [knownPeople, setKnownPeople] = useState<KnownPerson[]>([]);

  const [activeTab, setActiveTab] = useState<"friends" | "manual">("friends");
  const [showAddForm, setShowAddForm] = useState(false);
  const [showSendRequestForm, setShowSendRequestForm] = useState(false);
  const [newRequestEmail, setNewRequestEmail] = useState("");
  const [newRequestMessage, setNewRequestMessage] = useState("");

  const [newPerson, setNewPerson] = useState<KnownPerson>({
    name: "",
    nickname: "",
    email: "",
    relation: "",
    description: "",
    tone: "",
    birthday: "",
    discord_user_id: "",
    notes: "",
  });

  const [editingFriend, setEditingFriend] = useState<ConfirmedFriend | null>(null);
  const [editRelation, setEditRelation] = useState("");
  const [editNote, setEditNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      // Load friends system data
      const [friendsRes, incomingRes, outgoingRes, profileRes] = await Promise.all([
        apiFetch("/v1/friends", auth),
        apiFetch("/v1/friends/requests/incoming", auth),
        apiFetch("/v1/friends/requests/outgoing", auth),
        apiFetch("/v1/user/profile", auth),
      ]);

      if (friendsRes.ok) {
        const data = await friendsRes.json();
        setConfirmedFriends(data.friends || []);
      }
      if (incomingRes.ok) {
        const data = await incomingRes.json();
        setIncomingRequests(data.requests || []);
      }
      if (outgoingRes.ok) {
        const data = await outgoingRes.json();
        setOutgoingRequests(data.requests || []);
      }
      if (profileRes.ok) {
        const data = await profileRes.json();
        setKnownPeople(data.known_people || []);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:friendsLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [auth]);

  const sendFriendRequest = useCallback(async () => {
    if (!newRequestEmail.trim()) return;
    setSaving(true);
    try {
      const res = await apiFetch("/v1/friends/request", auth, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: newRequestEmail,
          message: newRequestMessage || null,
        }),
      });
      if (res.ok) {
        setNewRequestEmail("");
        setNewRequestMessage("");
        setShowSendRequestForm(false);
        void load();
      }
    } finally {
      setSaving(false);
    }
  }, [auth, newRequestEmail, newRequestMessage, load]);

  const acceptRequest = useCallback(async (requestId: number) => {
    try {
      await apiFetch(`/v1/friends/requests/${requestId}/accept`, auth, {
        method: "POST",
      });
      void load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:friendAcceptFailed"));
    }
  }, [auth, load]);

  const declineRequest = useCallback(async (requestId: number) => {
    try {
      await apiFetch(`/v1/friends/requests/${requestId}/decline`, auth, {
        method: "POST",
      });
      void load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:friendDeclineFailed"));
    }
  }, [auth, load]);

  const removeFriend = useCallback(async (friendUserId: string) => {
    try {
      await apiFetch(`/v1/friends/${friendUserId}`, auth, {
        method: "DELETE",
      });
      void load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:friendRemoveFailed"));
    }
  }, [auth, load]);

  const openEditFriend = useCallback((friend: ConfirmedFriend) => {
    setEditingFriend(friend);
    setEditRelation(friend.relation || "");
    setEditNote(friend.note || "");
  }, []);

  const saveEditFriend = useCallback(async () => {
    if (!editingFriend) return;
    setSaving(true);
    try {
      await apiFetch(`/v1/friends/${editingFriend.friend_user_id}`, auth, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          relation: editRelation.trim() || null,
          note: editNote.trim() || null,
        }),
      });
      setEditingFriend(null);
      void load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:friendSaveFailed"));
    } finally {
      setSaving(false);
    }
  }, [auth, editingFriend, editRelation, editNote, load]);

  const saveKnownPeople = useCallback(async (updated: KnownPerson[]) => {
    setSaving(true);
    try {
      await apiFetch("/v1/user/profile", auth, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ known_people: updated }),
      });
      setKnownPeople(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : t("settings:saveFailed"));
    } finally {
      setSaving(false);
    }
  }, [auth]);

  const addKnownPerson = () => {
    if (!newPerson.name.trim()) return;
    const updated = [...knownPeople, newPerson];
    void saveKnownPeople(updated);
    setNewPerson({
      name: "",
      nickname: "",
      email: "",
      relation: "",
      description: "",
      tone: "",
      birthday: "",
      discord_user_id: "",
      notes: "",
    });
    setShowAddForm(false);
  };

  const removeKnownPerson = (index: number) => {
    const updated = knownPeople.filter((_, i) => i !== index);
    void saveKnownPeople(updated);
  };

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-lg font-semibold text-white">{t("settings:friendsSystemTitle")}</h1>
        <p className="mt-2 text-sm text-surface-muted">{t("settings:friendsSystemSubtitle")}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-surface-border pb-1">
        <button
          type="button"
          onClick={() => setActiveTab("friends")}
          className={`px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === "friends"
              ? "text-white border-b-2 border-sky-500"
              : "text-surface-muted hover:text-white"
          }`}
        >
          {incomingRequests.length > 0
            ? t("settings:friendsTabFriendsCount", { count: incomingRequests.length })
            : t("settings:friendsTabFriends")}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("manual")}
          className={`px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === "manual"
              ? "text-white border-b-2 border-sky-500"
              : "text-surface-muted hover:text-white"
          }`}
        >
          {t("settings:friendsTabManual")}
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-surface-muted">{t("settings:agentLoading")}</p>
      ) : err ? (
        <p className="text-sm text-amber-400">{err}</p>
      ) : activeTab === "friends" ? (
        <div className="space-y-6">
          {/* Incoming Requests */}
          {incomingRequests.length > 0 && (
            <div className="rounded-xl border border-surface-border bg-surface-raised overflow-hidden">
              <div className="p-4 border-b border-surface-border">
                <h3 className="font-medium text-amber-300">{t("settings:friendsIncomingTitle")}</h3>
              </div>
              <div className="divide-y divide-surface-border">
                {incomingRequests.map((req) => (
                  <div key={req.id} className="p-4 flex items-center justify-between">
                    <div>
                      <div className="font-medium text-white">{req.display_name || req.email}</div>
                      {req.message && <div className="text-sm text-neutral-400 mt-1">{req.message}</div>}
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => acceptRequest(req.id)}
                        className="px-3 py-1.5 rounded bg-emerald-600 text-white text-sm hover:bg-emerald-500"
                      >
                        {t("settings:friendsAcceptBtn")}
                      </button>
                      <button
                        type="button"
                        onClick={() => declineRequest(req.id)}
                        className="px-3 py-1.5 rounded bg-neutral-700 text-white text-sm hover:bg-neutral-600"
                      >
                        {t("settings:friendsDeclineBtn")}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Outgoing Requests */}
          {outgoingRequests.length > 0 && (
            <div className="rounded-xl border border-surface-border bg-surface-raised overflow-hidden">
              <div className="p-4 border-b border-surface-border">
                <h3 className="font-medium text-sky-300">{t("settings:friendsOutgoingTitle")}</h3>
              </div>
              <div className="divide-y divide-surface-border">
                {outgoingRequests.map((req) => (
                  <div key={req.id} className="p-4">
                    <div className="font-medium text-white">{req.display_name || req.email}</div>
                    <div className="text-sm text-neutral-400 mt-1">{t("settings:friendsWaitingConfirmation")}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Send Request Button */}
          {showSendRequestForm ? (
            <div className="rounded-xl border border-surface-border bg-surface-raised p-5 space-y-4">
              <h3 className="font-medium text-white">{t("settings:friendsSendRequestTitle")}</h3>
              <div className="space-y-3">
                <input
                  type="email"
                  placeholder={t("settings:friendRequestEmailPlaceholder")}
                  value={newRequestEmail}
                  onChange={(e) => setNewRequestEmail(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                />
                <input
                  type="text"
                  placeholder={t("settings:friendRequestMessagePlaceholder")}
                  value={newRequestMessage}
                  onChange={(e) => setNewRequestMessage(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                />
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowSendRequestForm(false)}
                    className="px-4 py-2 rounded border border-white/10 text-sm text-neutral-300 hover:bg-white/5"
                  >
                    {t("settings:friendsCancelRequest")}
                  </button>
                  <button
                    type="button"
                    onClick={sendFriendRequest}
                    disabled={!newRequestEmail.trim() || saving}
                    className="px-4 py-2 rounded bg-sky-600 text-white text-sm hover:bg-sky-500 disabled:opacity-50"
                  >
                    {t("settings:friendsSendRequest")}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowSendRequestForm(true)}
              className="w-full py-3 rounded-xl border border-dashed border-white/20 text-surface-muted hover:border-white/40 hover:text-white text-sm"
            >
              {t("settings:friendsSendRequestBtn")}
            </button>
          )}

          {/* Confirmed Friends */}
          {confirmedFriends.length > 0 && (
            <div className="rounded-xl border border-surface-border bg-surface-raised overflow-hidden">
              <div className="p-4 border-b border-surface-border">
                <h3 className="font-medium text-emerald-300">✅ {t("settings:friendsConfirmedTitle")}</h3>
              </div>
              <div className="divide-y divide-surface-border">
                {confirmedFriends.map((friend) => (
                  <div key={friend.id} className="p-4 flex items-start justify-between group">
                    <div className="space-y-1">
                      <div className="font-medium text-white">
                        {friend.display_name || friend.email}
                      </div>
                      {friend.relation && (
                        <div className="text-sm text-neutral-400">{friend.relation}</div>
                      )}
                      {friend.email && (
                        <div className="text-xs text-neutral-500">{friend.email}</div>
                      )}
                    </div>
                    <div className="flex gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        onClick={() => openEditFriend(friend)}
                        className="text-xs text-sky-400 hover:text-sky-300"
                      >
                        {t("settings:friendsEditWithIcon")}
                      </button>
                      <button
                        type="button"
                        onClick={() => removeFriend(friend.friend_user_id)}
                        className="text-xs text-red-400 hover:text-red-300"
                      >
                        {t("settings:friendsRemove")}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {confirmedFriends.length === 0 && incomingRequests.length === 0 && outgoingRequests.length === 0 && (
            <div className="p-8 text-center text-surface-muted rounded-xl border border-surface-border bg-surface-raised">
              {t("settings:friendsEmptyStart")}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-6">
          <p className="text-sm text-surface-muted">
            Hier kannst du Personen manuell eintragen die nicht auf diesem System registriert sind.
            Diese Personen werden in jeden Chat mitgeschickt.
          </p>

          <div className="rounded-xl border border-surface-border bg-surface-raised overflow-hidden">
            {knownPeople.length === 0 ? (
              <div className="p-8 text-center text-surface-muted">
                {t("settings:friendsNoPeopleYet")}
              </div>
            ) : (
              <div className="divide-y divide-surface-border">
                {knownPeople.map((person, index) => (
                  <div
                    key={index}
                    className="p-4 flex items-start justify-between group hover:bg-white/[0.02]"
                  >
                    <div className="space-y-1 cursor-pointer flex-1">
                      <div className="font-medium text-white group-hover:text-sky-400">
                        {person.name}
                      </div>
                      {person.nickname && (
                        <div className="text-xs text-surface-muted">aka {person.nickname}</div>
                      )}
                      {person.relation && (
                        <div className="text-sm text-neutral-400">{person.relation}</div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => removeKnownPerson(index)}
                      className="text-xs text-red-400 hover:text-red-300"
                      disabled={saving}
                    >
                      {t("settings:friendsRemove")}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {showAddForm ? (
            <div className="rounded-xl border border-surface-border bg-surface-raised p-5 space-y-4">
              <h3 className="font-medium text-white">{t("settings:friendsNewPersonTitle")}</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-surface-muted">{t("settings:friendsNameRequired")}</label>
                  <input
                    type="text"
                    value={newPerson.name}
                    onChange={(e) => setNewPerson({ ...newPerson, name: e.target.value })}
                    className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                    placeholder={t("settings:friendNamePlaceholder")}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-surface-muted">{t("settings:friendsNicknameLabel")}</label>
                  <input
                    type="text"
                    value={newPerson.nickname}
                    onChange={(e) => setNewPerson({ ...newPerson, nickname: e.target.value })}
                    className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                    placeholder={t("settings:friendNicknamePlaceholder")}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-surface-muted">{t("settings:friendsEmailLabel")}</label>
                  <input
                    type="email"
                    value={newPerson.email}
                    onChange={(e) => setNewPerson({ ...newPerson, email: e.target.value })}
                    className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                    placeholder={t("settings:friendEmailPlaceholder")}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-surface-muted">{t("settings:friendsDiscordIdLabel")}</label>
                  <input
                    type="text"
                    value={newPerson.discord_user_id}
                    onChange={(e) => setNewPerson({ ...newPerson, discord_user_id: e.target.value })}
                    className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm font-mono"
                    placeholder={t("settings:friendPhonePlaceholder")}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-surface-muted">{t("settings:friendsRelationLabel")}</label>
                  <input
                    type="text"
                    value={newPerson.relation}
                    onChange={(e) => setNewPerson({ ...newPerson, relation: e.target.value })}
                    className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                    placeholder={t("settings:friendRelationPlaceholder")}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-surface-muted">{t("settings:friendsBirthdayLabel")}</label>
                  <input
                    type="date"
                    value={newPerson.birthday}
                    onChange={(e) => setNewPerson({ ...newPerson, birthday: e.target.value })}
                    className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs text-surface-muted">{t("settings:friendsDescriptionLabel")}</label>
                <textarea
                  value={newPerson.description}
                  onChange={(e) => setNewPerson({ ...newPerson, description: e.target.value })}
                  className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm min-h-[80px]"
                  placeholder={t("settings:friendDescriptionPlaceholder")}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs text-surface-muted">{t("settings:friendsToneFormLabel")}</label>
                <input
                  type="text"
                  value={newPerson.tone}
                  onChange={(e) => setNewPerson({ ...newPerson, tone: e.target.value })}
                  className="w-full px-3 py-2 rounded bg-black/30 border border-white/10 text-white text-sm"
                  placeholder={t("settings:friendTonePlaceholder")}
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="px-4 py-2 rounded border border-white/10 text-sm text-neutral-300 hover:bg-white/5"
                >
                  {t("settings:friendsCancel")}
                </button>
                <button
                  type="button"
                  onClick={addKnownPerson}
                  disabled={!newPerson.name.trim() || saving}
                  className="px-4 py-2 rounded bg-sky-600 text-white text-sm hover:bg-sky-500 disabled:opacity-50"
                >
                  {t("settings:friendsAdd")}
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowAddForm(true)}
              className="w-full py-3 rounded-xl border border-dashed border-white/20 text-surface-muted hover:border-white/40 hover:text-white text-sm"
            >
              {t("settings:friendsAddNewPerson")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
