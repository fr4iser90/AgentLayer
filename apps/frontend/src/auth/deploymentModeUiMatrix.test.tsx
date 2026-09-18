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
import { render, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { AuthUser } from "./AuthContext";
import { RequireOrgAdmin } from "./RequireOrgAdmin";
import { RequireUserAdmin } from "./RequireUserAdmin";
import { AdminLayout } from "../layout/AdminLayout";
import { UserMenu } from "../components/UserMenu";
import { AdminAgents } from "../pages/admin/AdminAgents";
import { AdminInterfacesLlmSection } from "../pages/admin/interfaces/AdminInterfacesLlmSection";
import { OperatorSettingsProvider } from "../features/admin/operatorSettings/OperatorSettingsProvider";

type MockAuthState = { user: AuthUser | null; loading: boolean; accessToken: string | null };
const authState = vi.hoisted<MockAuthState>(() => ({
  user: null,
  loading: false,
  accessToken: "tok",
}));

vi.mock("./AuthContext", () => ({
  useAuth: () => authState,
}));

// i18n: return the key so assertions are stable against locale changes.
// The returned object must be a stable identity. `AdminAgents.loadList` is a
// useCallback keyed on `[auth, t]`; a fresh `t` per render makes that effect
// re-fire forever, so the list flips back to `loading` as fast as it resolves
// and the policy grid never settles.
const i18nStub = vi.hoisted(() => ({
  t: (key: string) => key,
  i18n: {
    language: "en",
    resolvedLanguage: "en",
    changeLanguage: () => Promise.resolve(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => i18nStub,
}));

// UserMenu imports SUPPORTED from the i18n config module, which runs the real
// i18next bootstrap at import time. Mock the module, not the bootstrap.
vi.mock("../i18n/config", () => ({ SUPPORTED: ["en", "de"] }));

// One agent in the list so AdminAgents auto-selects it and renders the policy
// grid; two tenants so a tenant <select> has something to show when it is
// offered. Everything else stays empty — no handler fires in these mount-only
// assertions.
vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url === "/v1/admin/agents") {
        return {
          agents: [
            {
              id: "todo_agent",
              name: "Todo",
              icon: "check",
              description: "",
              min_role: "user",
              requires_workspace: false,
              tool_domains: [],
              tool_capability_any: [],
              tool_names_count: 0,
            },
          ],
        };
      }
      if (url.startsWith("/v1/admin/agents/todo_agent")) {
        return {
          id: "todo_agent",
          name: "Todo",
          system_prompt: "do the thing",
          governance: {
            access: {
              direct_allowed: true,
              delegate_allowed: false,
              direct_source: "role",
              delegate_source: "role",
            },
            prompt: { chars: 12, approx_tokens: 3, note: "" },
          },
        };
      }
      if (url === "/v1/admin/tenants") {
        return { tenants: [{ id: 1, name: "Alpha" }, { id: 2, name: "Beta" }] };
      }
      if (url === "/v1/admin/users") {
        return { users: [{ id: "u1", email: "admin@example.com" }] };
      }
      return {};
    },
  })),
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

/**
 * The two tenant pickers that had no deployment-mode check of any kind before
 * this change. They were invisible to an inventory of literal `deployment_mode`
 * comparisons — nothing in them compared against anything — so the only way to
 * prove the guard is wired is to render them.
 */
function optionValues(el: HTMLElement): string[] {
  return Array.from((el as HTMLSelectElement).options).map((o) => o.value);
}

async function renderAgentPolicy() {
  render(
    <MemoryRouter initialEntries={["/admin/agents"]}>
      <AdminAgents />
    </MemoryRouter>
  );
  return waitFor(() => screen.getByLabelText("admin:agentsPolicyScope"));
}

async function renderModelAccessScope() {
  render(
    <MemoryRouter initialEntries={["/admin/interfaces"]}>
      <OperatorSettingsProvider>
        <AdminInterfacesLlmSection mode="policies" />
      </OperatorSettingsProvider>
    </MemoryRouter>
  );
  return waitFor(() => screen.getByLabelText("admin:modelAccessScope"));
}

const ORG_MODES = MODES.filter((m) => m === "multi_tenant");
const NO_ORG_MODES = MODES.filter((m) => m !== "multi_tenant");

describe("agent access-policy scope picker", () => {
  it.each(NO_ORG_MODES)("%s: no tenant option offered", async (mode) => {
    authState.user = userIn(mode);
    expect(optionValues(await renderAgentPolicy())).not.toContain("tenant");
  });

  it.each(ORG_MODES)("%s: tenant option offered", async (mode) => {
    authState.user = userIn(mode);
    expect(optionValues(await renderAgentPolicy())).toContain("tenant");
  });

  /**
   * The one that actually bites. `policyScope` defaults to `"tenant"`, so
   * hiding the option without retiring the value would leave a select showing
   * nothing while still submitting `tenant`.
   */
  it.each(NO_ORG_MODES)(
    "%s: the tenant default is coerced to global, not left dangling",
    async (mode) => {
      authState.user = userIn(mode);
      const select = (await renderAgentPolicy()) as HTMLSelectElement;
      expect(select.value).toBe("global");
    }
  );

  it("multi_tenant: the tenant default is kept", async () => {
    authState.user = userIn("multi_tenant");
    const select = (await renderAgentPolicy()) as HTMLSelectElement;
    expect(select.value).toBe("tenant");
  });

  it.each(NO_ORG_MODES)("%s: the free-text tenant id field is gone too", async (mode) => {
    authState.user = userIn(mode);
    await renderAgentPolicy();
    expect(screen.queryByLabelText("admin:agentsTenantId")).toBeNull();
  });

  it("multi_tenant: the free-text tenant id field is present", async () => {
    authState.user = userIn("multi_tenant");
    await renderAgentPolicy();
    expect(screen.getByLabelText("admin:agentsTenantId")).toBeInTheDocument();
  });
});

describe("model-access scope picker", () => {
  it.each(NO_ORG_MODES)("%s: no tenant option offered", async (mode) => {
    authState.user = userIn(mode);
    expect(optionValues(await renderModelAccessScope())).not.toContain("tenant");
  });

  it.each(ORG_MODES)("%s: tenant option offered", async (mode) => {
    authState.user = userIn(mode);
    expect(optionValues(await renderModelAccessScope())).toContain("tenant");
  });

  it("multi_tenant: choosing tenant reveals the tenant select", async () => {
    authState.user = userIn("multi_tenant");
    const select = await renderModelAccessScope();
    fireEvent.change(select, { target: { value: "tenant" } });
    expect(screen.getByLabelText("admin:modelAccessTenant")).toBeInTheDocument();
  });

  it("no org surface: the tenant select can never appear", async () => {
    for (const mode of NO_ORG_MODES) {
      authState.user = userIn(mode);
      const select = await renderModelAccessScope();
      // Not offered, so it cannot be selected — and the dependent select stays away.
      expect(optionValues(select)).not.toContain("tenant");
      expect(screen.queryByLabelText("admin:modelAccessTenant")).toBeNull();
    }
  });
});

/** no mode is half-blocked **/
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
