import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleCheck } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/EmptyState";

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
    <div className="mx-auto max-w-page space-y-deep">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">{t("settings:friendsSystemTitle")}</h1>
        <p className="mt-base text-sm text-ink-muted">{t("settings:friendsSystemSubtitle")}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-wide border-b border-line pb-tight">
        <button
          type="button"
          onClick={() => setActiveTab("friends")}
          className={`px-soft py-base text-sm font-medium transition-colors ${
            activeTab === "friends"
              ? "text-ink-primary border-b-2 border-accent"
              : "text-ink-muted hover:text-white"
          }`}
        >
          {incomingRequests.length > 0
            ? t("settings:friendsTabFriendsCount", { count: incomingRequests.length })
            : t("settings:friendsTabFriends")}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("manual")}
          className={`px-soft py-base text-sm font-medium transition-colors ${
            activeTab === "manual"
              ? "text-ink-primary border-b-2 border-accent"
              : "text-ink-muted hover:text-white"
          }`}
        >
          {t("settings:friendsTabManual")}
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-ink-muted">{t("settings:agentLoading")}</p>
      ) : err ? (
        <p className="text-sm text-warning">{err}</p>
      ) : activeTab === "friends" ? (
        <div className="space-y-broad">
          {/* Incoming Requests */}
          {incomingRequests.length > 0 && (
            <div className="rounded-sheet border border-line bg-card overflow-hidden">
              <div className="p-wide border-b border-line">
                <h3 className="font-medium text-badge-warning">{t("settings:friendsIncomingTitle")}</h3>
              </div>
              <div className="divide-y divide-line">
                {incomingRequests.map((req) => (
                  <div key={req.id} className="p-wide flex items-center justify-between">
                    <div>
                      <div className="font-medium text-ink-primary">{req.display_name || req.email}</div>
                      {req.message && <div className="text-sm text-ink-muted mt-tight">{req.message}</div>}
                    </div>
                    <div className="flex gap-base">
                      <button
                        type="button"
                        onClick={() => acceptRequest(req.id)}
                        className="px-soft py-snug rounded-tile bg-success text-ink-on-fill text-sm hover:bg-success-hover"
                      >
                        {t("settings:friendsAcceptBtn")}
                      </button>
                      <button
                        type="button"
                        onClick={() => declineRequest(req.id)}
                        className="px-soft py-snug rounded-tile bg-neutral-700 text-ink-primary text-sm hover:bg-neutral-600"
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
            <div className="rounded-sheet border border-line bg-card overflow-hidden">
              <div className="p-wide border-b border-line">
                <h3 className="font-medium text-badge-accent">{t("settings:friendsOutgoingTitle")}</h3>
              </div>
              <div className="divide-y divide-line">
                {outgoingRequests.map((req) => (
                  <div key={req.id} className="p-wide">
                    <div className="font-medium text-ink-primary">{req.display_name || req.email}</div>
                    <div className="text-sm text-ink-muted mt-tight">{t("settings:friendsWaitingConfirmation")}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Send Request Button */}
          {showSendRequestForm ? (
            <div className="rounded-sheet border border-line bg-card p-roomy space-y-wide">
              <h3 className="font-medium text-ink-primary">{t("settings:friendsSendRequestTitle")}</h3>
              <div className="space-y-soft">
                <input
                  type="email"
                  placeholder={t("settings:friendRequestEmailPlaceholder")}
                  value={newRequestEmail}
                  onChange={(e) => setNewRequestEmail(e.target.value)}
                  className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                />
                <input
                  type="text"
                  placeholder={t("settings:friendRequestMessagePlaceholder")}
                  value={newRequestMessage}
                  onChange={(e) => setNewRequestMessage(e.target.value)}
                  className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                />
                <div className="flex justify-end gap-soft pt-base">
                  <Button
                    type="button"
                    variant="secondary"
                    size="lg"
                    onClick={() => setShowSendRequestForm(false)}
                  >
                    {t("settings:friendsCancelRequest")}
                  </Button>
                  <button
                    type="button"
                    onClick={sendFriendRequest}
                    disabled={!newRequestEmail.trim() || saving}
                    className="px-wide py-base rounded-tile bg-accent text-ink-on-fill text-sm hover:bg-accent-hover disabled:opacity-50"
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
              className="w-full py-soft rounded-sheet border border-dashed border-line-strong text-ink-muted hover:border-white/40 hover:text-white text-sm"
            >
              {t("settings:friendsSendRequestBtn")}
            </button>
          )}

          {/* Confirmed Friends */}
          {confirmedFriends.length > 0 && (
            <div className="rounded-sheet border border-line bg-card overflow-hidden">
              <div className="p-wide border-b border-line">
                <h3 className="flex items-center gap-snug font-medium text-badge-success">
                  <CircleCheck aria-hidden className="h-4 w-4" />
                  {t("settings:friendsConfirmedTitle")}
                </h3>
              </div>
              <div className="divide-y divide-line">
                {confirmedFriends.map((friend) => (
                  <div key={friend.id} className="p-wide flex items-start justify-between group">
                    <div className="space-y-tight">
                      <div className="font-medium text-ink-primary">
                        {friend.display_name || friend.email}
                      </div>
                      {friend.relation && (
                        <div className="text-sm text-ink-muted">{friend.relation}</div>
                      )}
                      {friend.email && (
                        <div className="text-xs text-ink-muted">{friend.email}</div>
                      )}
                    </div>
                    <div className="flex gap-soft opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        onClick={() => openEditFriend(friend)}
                        className="text-xs text-accent hover:text-badge-accent"
                      >
                        {t("settings:friendsEditWithIcon")}
                      </button>
                      <Button
                        type="button"
                        variant="danger"
                        size="sm"
                        onClick={() => removeFriend(friend.friend_user_id)}
                      >
                        {t("settings:friendsRemove")}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {confirmedFriends.length === 0 && incomingRequests.length === 0 && outgoingRequests.length === 0 && (
            <div className="rounded-sheet border border-line bg-card">
              <EmptyState
                pose="waiting"
                title={t("settings:friendsEmptyStart")}
                animated={false}
                size={56}
              />
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-broad">
          <p className="text-sm text-ink-muted">
            {t("settings:friendsManualIntro")}
          </p>

          <div className="rounded-sheet border border-line bg-card overflow-hidden">
            {knownPeople.length === 0 ? (
              <EmptyState
                pose="empty"
                title={t("settings:friendsNoPeopleYet")}
                animated={false}
                size={56}
              />
            ) : (
              <div className="divide-y divide-line">
                {knownPeople.map((person, index) => (
                  <div
                    key={index}
                    className="p-wide flex items-start justify-between group hover:bg-white/[0.02]"
                  >
                    <div className="space-y-tight cursor-pointer flex-1">
                      <div className="font-medium text-ink-primary group-hover:text-accent">
                        {person.name}
                      </div>
                      {person.nickname && (
                        <div className="text-xs text-ink-muted">aka {person.nickname}</div>
                      )}
                      {person.relation && (
                        <div className="text-sm text-ink-muted">{person.relation}</div>
                      )}
                    </div>
                    <Button
                      type="button"
                      variant="danger"
                      size="sm"
                      onClick={() => removeKnownPerson(index)}
                      disabled={saving}
                    >
                      {t("settings:friendsRemove")}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {showAddForm ? (
            <div className="rounded-sheet border border-line bg-card p-roomy space-y-wide">
              <h3 className="font-medium text-ink-primary">{t("settings:friendsNewPersonTitle")}</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-wide">
                <div className="space-y-tight">
                  <label className="text-xs text-ink-muted">{t("settings:friendsNameRequired")}</label>
                  <input
                    type="text"
                    value={newPerson.name}
                    onChange={(e) => setNewPerson({ ...newPerson, name: e.target.value })}
                    className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                    placeholder={t("settings:friendNamePlaceholder")}
                  />
                </div>
                <div className="space-y-tight">
                  <label className="text-xs text-ink-muted">{t("settings:friendsNicknameLabel")}</label>
                  <input
                    type="text"
                    value={newPerson.nickname}
                    onChange={(e) => setNewPerson({ ...newPerson, nickname: e.target.value })}
                    className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                    placeholder={t("settings:friendNicknamePlaceholder")}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-wide">
                <div className="space-y-tight">
                  <label className="text-xs text-ink-muted">{t("settings:friendsEmailLabel")}</label>
                  <input
                    type="email"
                    value={newPerson.email}
                    onChange={(e) => setNewPerson({ ...newPerson, email: e.target.value })}
                    className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                    placeholder={t("settings:friendEmailPlaceholder")}
                  />
                </div>
                <div className="space-y-tight">
                  <label className="text-xs text-ink-muted">{t("settings:friendsDiscordIdLabel")}</label>
                  <input
                    type="text"
                    value={newPerson.discord_user_id}
                    onChange={(e) => setNewPerson({ ...newPerson, discord_user_id: e.target.value })}
                    className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm font-mono"
                    placeholder={t("settings:friendPhonePlaceholder")}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-wide">
                <div className="space-y-tight">
                  <label className="text-xs text-ink-muted">{t("settings:friendsRelationLabel")}</label>
                  <input
                    type="text"
                    value={newPerson.relation}
                    onChange={(e) => setNewPerson({ ...newPerson, relation: e.target.value })}
                    className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                    placeholder={t("settings:friendRelationPlaceholder")}
                  />
                </div>
                <div className="space-y-tight">
                  <label className="text-xs text-ink-muted">{t("settings:friendsBirthdayLabel")}</label>
                  <input
                    type="date"
                    value={newPerson.birthday}
                    onChange={(e) => setNewPerson({ ...newPerson, birthday: e.target.value })}
                    className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                  />
                </div>
              </div>

              <div className="space-y-tight">
                <label className="text-xs text-ink-muted">{t("settings:friendsDescriptionLabel")}</label>
                <textarea
                  value={newPerson.description}
                  onChange={(e) => setNewPerson({ ...newPerson, description: e.target.value })}
                  className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm min-h-[80px]"
                  placeholder={t("settings:friendDescriptionPlaceholder")}
                />
              </div>

              <div className="space-y-tight">
                <label className="text-xs text-ink-muted">{t("settings:friendsToneFormLabel")}</label>
                <input
                  type="text"
                  value={newPerson.tone}
                  onChange={(e) => setNewPerson({ ...newPerson, tone: e.target.value })}
                  className="w-full px-soft py-base rounded-tile bg-field border border-line text-ink-primary text-sm"
                  placeholder={t("settings:friendTonePlaceholder")}
                />
              </div>

              <div className="flex justify-end gap-soft pt-base">
                <Button
                  type="button"
                  variant="secondary"
                  size="lg"
                  onClick={() => setShowAddForm(false)}
                >
                  {t("settings:friendsCancel")}
                </Button>
                <button
                  type="button"
                  onClick={addKnownPerson}
                  disabled={!newPerson.name.trim() || saving}
                  className="px-wide py-base rounded-tile bg-accent text-ink-on-fill text-sm hover:bg-accent-hover disabled:opacity-50"
                >
                  {t("settings:friendsAdd")}
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowAddForm(true)}
              className="w-full py-soft rounded-sheet border border-dashed border-line-strong text-ink-muted hover:border-white/40 hover:text-white text-sm"
            >
              {t("settings:friendsAddNewPerson")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
