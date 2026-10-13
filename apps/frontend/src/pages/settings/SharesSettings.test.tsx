import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { AuthUser } from "../../auth/AuthContext";
import SharesSettings from "./SharesSettings";
import { apiFetch } from "../../lib/api";

/**
 * The share UI is driven by the backend adapter registry rather than a
 * hand-maintained list. These tests pin the two things that used to be wrong:
 *
 *  - the policy editor rendered days_ahead and expires_at for *every* type,
 *    so a user could set days_ahead on a dashboard share, which the
 *    dashboard adapter does not read and the backend rejects at grant time;
 *  - the "add resource" control was free text, letting a user create a grant
 *    for a type with no adapter, which does nothing at all.
 *
 * Stable identities across renders: `load` is a useCallback keyed on
 * [auth, lang, t], so a fresh `useAuth`/`t` object each render would make it
 * a new callback every time and re-fire the load effect forever — the page
 * would spin with no output rather than fail.
 */
type MockAuthState = { user: AuthUser | null; loading: boolean; accessToken: string };
const authState = vi.hoisted<MockAuthState>(() => ({
  user: null,
  loading: false,
  accessToken: "tok",
}));
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));
const i18nState = vi.hoisted(() => ({ language: "en" }));

vi.mock("../../auth/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: tMock.t, i18n: i18nState }),
}));
vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);

const CATALOG = [
  {
    id: "collection",
    name: "collection",
    default_identifier: null,
    policy_fields: ["expires_at", "permission"],
    listable: false,
    aliases: [],
  },
  {
    id: "dashboard",
    name: "dashboard",
    default_identifier: null,
    policy_fields: ["block_ids", "expires_at", "permission"],
    listable: true,
    aliases: [],
  },
  {
    id: "google_calendar",
    name: "google calendar",
    default_identifier: "primary",
    policy_fields: ["days_ahead", "expires_at"],
    listable: false,
    aliases: ["calendar"],
  },
];

const OUTGOING = [
  {
    resource_type: "google_calendar",
    resource_identifier: "primary",
    policy: { days_ahead: 14 },
    grantee_user_id: "friend-1",
    email: "anna@nord.example",
    display_name: "Anna Nord",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    resource_type: "dashboard",
    resource_identifier: "dash-1",
    policy: { permission: "edit", block_ids: ["block-shifts"] },
    grantee_user_id: "friend-1",
    email: "anna@nord.example",
    display_name: "Anna Nord",
    created_at: "2026-01-01T00:00:00Z",
  },
];

const FRIEND_SHARES = {
  outgoing: ["google_calendar", "dashboard"],
  incoming: [],
  outgoing_grants: [
    {
      resource_type: "google_calendar",
      resource_identifier: "primary",
      policy: { days_ahead: 14 },
    },
    {
      resource_type: "dashboard",
      resource_identifier: "dash-1",
      policy: { permission: "edit", block_ids: ["block-shifts"] },
    },
  ],
  incoming_grants: [],
};

function json(body: unknown) {
  return { ok: true, json: async () => body, text: async () => "" } as unknown as Response;
}

function installRoutes(setBody: unknown = { ok: true, policy: {} }) {
  api.mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.startsWith("/v1/shares/catalog")) return json({ ok: true, resources: CATALOG });
    if (u.startsWith("/v1/shares/outgoing")) return json({ ok: true, shares: OUTGOING });
    if (u.startsWith("/v1/shares/incoming")) return json({ ok: true, shares: [] });
    if (u.startsWith("/v1/shares/friend/")) return json(FRIEND_SHARES);
    if (u.startsWith("/v1/friends")) return json({ ok: true, friends: [] });
    if (u === "/v1/shares/set") return json(setBody);
    return json({ ok: true });
  });
}

async function openFriendPanel() {
  render(
    <MemoryRouter>
      <SharesSettings />
    </MemoryRouter>,
  );
  const card = await screen.findByText("Anna Nord");
  fireEvent.click(card.closest("div.cursor-pointer") as Element);
  await screen.findByText("settings:sharesManageFriend");
}

beforeEach(() => {
  vi.clearAllMocks();
  installRoutes();
});

it("renders each type's own policy fields, not one fixed pair", async () => {
  await openFriendPanel();

  // days_ahead belongs to the calendar only. Before the registry drove this
  // it rendered for the dashboard too, offering an input the backend rejects.
  await waitFor(() => {
    expect(screen.getAllByText("settings:sharesDaysAhead")).toHaveLength(1);
  });
  // block_ids and permission belong to the dashboard only.
  expect(screen.getAllByText("settings:sharesBlockIds")).toHaveLength(1);
  expect(screen.getAllByText("settings:sharesPermission")).toHaveLength(1);
  // expires_at is honoured by both granted types.
  expect(screen.getAllByText("settings:sharesExpiresAt")).toHaveLength(2);
});

it("offers a closed picker over registered types instead of free text", async () => {
  await openFriendPanel();

  const picker = await screen.findByLabelText("settings:sharesSelectResourceType");
  expect(picker.tagName).toBe("SELECT");

  const options = Array.from((picker as HTMLSelectElement).options)
    .map((o) => o.value)
    .filter(Boolean)
    .sort();
  // Canonical ids only — the legacy "calendar" alias must not appear as a
  // second thing to share.
  expect(options).toEqual(["collection", "dashboard", "google_calendar"]);
});

it("requires an identifier for a type that has no usable default", async () => {
  await openFriendPanel();

  const picker = await screen.findByLabelText("settings:sharesSelectResourceType");
  const shareButton = screen.getByText("settings:sharesAddResource").closest("button") as HTMLButtonElement;

  // A collection share needs a slug; the calendar's "primary" default does
  // not apply, so the field must be demanded rather than guessed.
  fireEvent.change(picker, { target: { value: "collection" } });
  const ident = await screen.findByLabelText("settings:sharesIdentifier");
  expect(ident).toBeTruthy();
  expect(shareButton.disabled).toBe(true);

  fireEvent.change(ident, { target: { value: "haustiere" } });
  await waitFor(() => expect(shareButton.disabled).toBe(false));
});

it("does not ask for an identifier when the adapter supplies one", async () => {
  await openFriendPanel();

  const picker = await screen.findByLabelText("settings:sharesSelectResourceType");
  fireEvent.change(picker, { target: { value: "google_calendar" } });

  const shareButton = screen.getByText("settings:sharesAddResource").closest("button") as HTMLButtonElement;
  expect(screen.queryByLabelText("settings:sharesIdentifier")).toBeNull();
  expect(shareButton.disabled).toBe(false);
});

it("sends the adapter's default identifier rather than a hardcoded one", async () => {
  await openFriendPanel();

  const picker = await screen.findByLabelText("settings:sharesSelectResourceType");
  fireEvent.change(picker, { target: { value: "collection" } });
  const ident = await screen.findByLabelText("settings:sharesIdentifier");
  fireEvent.change(ident, { target: { value: "haustiere" } });

  const shareButton = screen.getByText("settings:sharesAddResource").closest("button") as HTMLButtonElement;
  fireEvent.click(shareButton);

  await waitFor(() => expect(api).toHaveBeenCalledWith(
    "/v1/shares/set",
    expect.anything(),
    expect.objectContaining({ method: "POST" }),
  ));

  const call = api.mock.calls.find((c) => String(c[0]) === "/v1/shares/set");
  const body = JSON.parse((call?.[2] as { body: string }).body);
  expect(body.resource_type).toBe("collection");
  expect(body.resource_identifier).toBe("haustiere");
});

const PUBLISHED_CALENDAR = {
  resource_type: "google_calendar",
  resource_identifier: "primary",
  projection_kind: "events",
  available_kinds: ["events", "availability"],
  default_kind: "events",
  generated_at: "2026-01-01T00:00:00Z",
  expires_at: "2099-01-01T00:00:00Z",
  fresh: true,
};

function installPublished(projections: unknown[]) {
  api.mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.startsWith("/v1/shares/catalog")) return json({ ok: true, resources: CATALOG });
    if (u.startsWith("/v1/shares/projections")) return json({ ok: true, projections });
    if (u.startsWith("/v1/shares/outgoing")) return json({ ok: true, shares: OUTGOING });
    if (u.startsWith("/v1/shares/incoming")) return json({ ok: true, shares: [] });
    if (u.startsWith("/v1/shares/friend/")) return json(FRIEND_SHARES);
    if (u.startsWith("/v1/friends")) return json({ ok: true, friends: [] });
    return json({ ok: true });
  });
}

it("shows the owner's published views without opening a friend panel", async () => {
  // The shape belongs to the resource, not to a friendship. If this only
  // appeared inside the per-friend editor it would imply the owner can
  // give one friend the narrow view and another the wide one, which the
  // model does not allow.
  installPublished([PUBLISHED_CALENDAR]);
  render(
    <MemoryRouter>
      <SharesSettings />
    </MemoryRouter>,
  );

  await screen.findByText("settings:sharesPublishedTitle");
  const picker = await screen.findByLabelText("settings:sharesPublishedKind");
  expect((picker as HTMLSelectElement).value).toBe("events");
});

it("offers only the kinds this adapter actually publishes", async () => {
  installPublished([PUBLISHED_CALENDAR]);
  render(
    <MemoryRouter>
      <SharesSettings />
    </MemoryRouter>,
  );

  const picker = (await screen.findByLabelText("settings:sharesPublishedKind")) as HTMLSelectElement;
  expect(Array.from(picker.options).map((o) => o.value).sort()).toEqual([
    "availability",
    "events",
  ]);
});

it("publishes the chosen kind to the projection endpoint", async () => {
  installPublished([PUBLISHED_CALENDAR]);
  render(
    <MemoryRouter>
      <SharesSettings />
    </MemoryRouter>,
  );

  const picker = (await screen.findByLabelText("settings:sharesPublishedKind")) as HTMLSelectElement;
  const button = screen.getByText("settings:sharesPublishButton").closest("button") as HTMLButtonElement;
  // Nothing chosen yet, so nothing to publish.
  expect(button.disabled).toBe(true);

  fireEvent.change(picker, { target: { value: "availability" } });
  await waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.click(button);

  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/v1/shares/projection",
      expect.anything(),
      expect.objectContaining({ method: "POST" }),
    ),
  );
  const call = api.mock.calls.find((c) => String(c[0]) === "/v1/shares/projection");
  const body = JSON.parse((call?.[2] as { body: string }).body);
  expect(body).toEqual({
    resource_type: "google_calendar",
    resource_identifier: "primary",
    projection_kind: "availability",
  });
});

it("marks a view past its bound as not current", async () => {
  installPublished([{ ...PUBLISHED_CALENDAR, fresh: false }]);
  render(
    <MemoryRouter>
      <SharesSettings />
    </MemoryRouter>,
  );

  await screen.findByText("settings:sharesPublishedStale");
  expect(screen.queryByText("settings:sharesPublishedFresh")).toBeNull();
});

it("says so when the owner has published nothing", async () => {
  installPublished([]);
  render(
    <MemoryRouter>
      <SharesSettings />
    </MemoryRouter>,
  );

  await screen.findByText("settings:sharesPublishedNone");
  expect(screen.queryByLabelText("settings:sharesPublishedKind")).toBeNull();
});

it("resolves a legacy alias grant to its canonical catalog entry", async () => {
  // A grant written years ago under "calendar" must still render as the
  // google_calendar type with its policy fields, not as an unknown type.
  installRoutes();
  api.mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.startsWith("/v1/shares/catalog")) return json({ ok: true, resources: CATALOG });
    if (u.startsWith("/v1/shares/outgoing")) return json({ ok: true, shares: [] });
    if (u.startsWith("/v1/shares/incoming")) return json({ ok: true, shares: [] });
    if (u.startsWith("/v1/shares/friend/"))
      return json({
        outgoing: ["calendar"],
        incoming: [],
        outgoing_grants: [
          { resource_type: "calendar", resource_identifier: "primary", policy: { days_ahead: 7 } },
        ],
        incoming_grants: [],
      });
    if (u.startsWith("/v1/friends"))
      return json({
        ok: true,
        friends: [
          {
            friend_user_id: "friend-1",
            email: "anna@nord.example",
            display_name: "Anna Nord",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      });
    return json({ ok: true });
  });

  render(
    <MemoryRouter>
      <SharesSettings />
    </MemoryRouter>,
  );
  const card = await screen.findByText("Anna Nord");
  fireEvent.click(card.closest("div.cursor-pointer") as Element);
  await screen.findByText("settings:sharesManageFriend");

  // Named by the canonical entry. The id shows in both the "you share" and
  // "they share" listings, so assert every occurrence resolved to the
  // canonical name rather than the raw "calendar" string.
  const named = await screen.findAllByText("google calendar");
  expect(named.length).toBeGreaterThan(0);
  expect(screen.queryByText("calendar")).toBeNull();
  // And it got the calendar's policy fields, not an empty set.
  expect(screen.getAllByText("settings:sharesDaysAhead")).toHaveLength(1);
  expect(screen.queryByText("settings:sharesBlockIds")).toBeNull();
});
