/**
 * Rendered-UI matrix for the three deployment modes.
 *
 * The predicate unit tests prove what `hasOrgSurface` / `isSingleUser` return.
 * They do not prove that a component actually hides what we think it hides —
 * that is a wiring question, and wiring is exactly where a `=== "agent_system"`
 * left `/org` reachable for a mode nobody had considered. These render the real
 * components and routes under each mode and assert what a user can see.
 *
 * `deploymentMode.ts` is deliberately NOT mocked: the real predicates run
 * against a real-shaped `AuthUser`, so a change to either layer shows up here.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { AuthUser } from "./AuthContext";
import { RequireOrgAdmin } from "./RequireOrgAdmin";
import { RequireUserAdmin } from "./RequireUserAdmin";
import { AdminLayout } from "../layout/AdminLayout";
import { UserMenu } from "../components/UserMenu";

type MockAuthState = { user: AuthUser | null; loading: boolean; accessToken: string | null };
const authState = vi.hoisted<MockAuthState>(() => ({
  user: null,
  loading: false,
  accessToken: "tok",
}));

vi.mock("./AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: "en",
      resolvedLanguage: "en",
      changeLanguage: () => Promise.resolve(),
    },
  }),
}));

// UserMenu imports SUPPORTED from the i18n config module, which runs the real
// i18next bootstrap at import time. Mock the module, not the bootstrap.
vi.mock("../i18n/config", () => ({ SUPPORTED: ["en", "de"] }));

vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(async () => ({ ok: true, json: async () => ({}) })),
}));

/** A site admin who is also a tenant owner, so only the mode can block anything. */
function userIn(mode: string): AuthUser {
  return {
    id: "u1",
    email: "admin@example.com",
    role: "admin",
    site_role: "site_admin",
    capabilities: ["user.manage", "agent.assign"],
    tenant_id: 1,
    membership_role: "tenant_owner",
    deployment_mode: mode,
  } as AuthUser;
}

const MODES = ["single_user", "agent_system", "multi_tenant"] as const;

function renderOrgRoute() {
  return render(
    <MemoryRouter initialEntries={["/org/knowledge"]}>
      <Routes>
        <Route path="/org" element={<RequireOrgAdmin />}>
          <Route path="knowledge" element={<div>ORG-CONTENT</div>} />
        </Route>
        <Route path="/chat" element={<div>AT-CHAT</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function renderUsersRoute() {
  return render(
    <MemoryRouter initialEntries={["/admin/users"]}>
      <Routes>
        <Route
          path="/admin/users"
          element={<RequireUserAdmin><div>USERS-PAGE</div></RequireUserAdmin>}
        />
        <Route path="/admin" element={<div>AT-ADMIN</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function renderAdminChrome() {
  return render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<div>ADMIN-INDEX</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  authState.loading = false;
  authState.accessToken = "tok";
});

describe("/org surface", () => {
  it("single_user cannot reach /org", () => {
    authState.user = userIn("single_user");
    renderOrgRoute();
    expect(screen.queryByText("ORG-CONTENT")).toBeNull();
    expect(screen.getByText("AT-CHAT")).toBeInTheDocument();
  });

  it("agent_system cannot reach /org", () => {
    authState.user = userIn("agent_system");
    renderOrgRoute();
    expect(screen.queryByText("ORG-CONTENT")).toBeNull();
    expect(screen.getByText("AT-CHAT")).toBeInTheDocument();
  });

  it("multi_tenant reaches /org", () => {
    authState.user = userIn("multi_tenant");
    renderOrgRoute();
    expect(screen.getByText("ORG-CONTENT")).toBeInTheDocument();
  });
});

describe("/admin/users", () => {
  it("single_user is bounced to /admin", () => {
    authState.user = userIn("single_user");
    renderUsersRoute();
    expect(screen.queryByText("USERS-PAGE")).toBeNull();
    expect(screen.getByText("AT-ADMIN")).toBeInTheDocument();
  });

  it.each(MODES.filter((m) => m !== "single_user"))(
    "%s renders the users page",
    (mode) => {
      authState.user = userIn(mode);
      renderUsersRoute();
      expect(screen.getByText("USERS-PAGE")).toBeInTheDocument();
    }
  );
});

describe("admin sidebar People group", () => {
  it("hidden for single_user", () => {
    authState.user = userIn("single_user");
    renderAdminChrome();
    expect(screen.queryByText("admin:navPeople")).toBeNull();
    // the rest of the sidebar is untouched
    expect(screen.getByText("admin:agentsTitle")).toBeInTheDocument();
  });

  it.each(MODES.filter((m) => m !== "single_user"))(
    "shown for %s",
    (mode) => {
      authState.user = userIn(mode);
      renderAdminChrome();
      expect(screen.getByText("admin:navPeople")).toBeInTheDocument();
    }
  );
});

/** The dropdown renders its items only when open, so open it before asserting. */
function renderOpenMenu() {
  const utils = render(
    <MemoryRouter initialEntries={["/chat"]}>
      <UserMenu />
    </MemoryRouter>
  );
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  return utils;
}

describe("user dropdown organization link", () => {
  it.each(MODES.filter((m) => m !== "multi_tenant"))(
    "hidden for %s",
    (mode) => {
      authState.user = userIn(mode);
      renderOpenMenu();
      expect(screen.queryByText("userMenu.organization")).toBeNull();
    }
  );

  it("shown for multi_tenant", () => {
    authState.user = userIn("multi_tenant");
    renderOpenMenu();
    expect(screen.getByText("userMenu.organization")).toBeInTheDocument();
  });
});

describe("no mode is half-blocked", () => {
  /**
   * The three surfaces must agree with each other. A mode that hides the nav
   * entry but leaves the route reachable is the exact bug class this guards.
   */
  const expected = {
    single_user: { orgBlocked: true, usersBlocked: true, peopleNav: false, orgLink: false },
    agent_system: { orgBlocked: true, usersBlocked: false, peopleNav: true, orgLink: false },
    multi_tenant: { orgBlocked: false, usersBlocked: false, peopleNav: true, orgLink: true },
  } as const;

  it.each(MODES)("%s matches the intended matrix", (mode) => {
    const want = expected[mode];
    authState.user = userIn(mode);

    const org = renderOrgRoute();
    const orgBlocked = screen.queryByText("ORG-CONTENT") === null;
    org.unmount();

    const users = renderUsersRoute();
    const usersBlocked = screen.queryByText("USERS-PAGE") === null;
    users.unmount();

    const chrome = renderAdminChrome();
    const peopleNav = screen.queryByText("admin:navPeople") !== null;
    chrome.unmount();

    const menu = renderOpenMenu();
    const orgLink = screen.queryByText("userMenu.organization") !== null;
    menu.unmount();

    expect({ orgBlocked, usersBlocked, peopleNav, orgLink }).toEqual({
      orgBlocked: want.orgBlocked,
      usersBlocked: want.usersBlocked,
      peopleNav: want.peopleNav,
      orgLink: want.orgLink,
    });
  });
});

/** A mode nobody declared must not be treated as single_user by accident. */
describe("unknown mode", () => {
  it("falls back to the widest surface, like the backend reader", () => {
    authState.user = userIn("solo");
    renderOrgRoute();
    expect(screen.getByText("ORG-CONTENT")).toBeInTheDocument();
  });
});
