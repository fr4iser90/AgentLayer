import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { AuthUser } from "../../auth/AuthContext";
import { AdminUsers } from "./AdminUsers";

// Stable identity across re-renders. The page's `reloadAll` effect depends on the
// `useAuth` return value; if that is a new object every render (as a plain
// `() => ({ user, loading })` factory would produce), the effect re-runs on every
// render and toggles `listLoading` back to the "loading" row. `vi.hoisted` gives
// us one object whose `user` we mutate per test, keeping identity stable.
type MockAuthState = { user: AuthUser | null; loading: boolean };
const authState = vi.hoisted<MockAuthState>(() => ({ user: null, loading: false }));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => authState,
}));

// i18n: return the key so assertions are stable against locale changes.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// API: respond with two users on the list endpoints; empty elsewhere so no
// interaction handler ever fires during these mount-only assertions.
vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url === "/v1/admin/users") {
        return {
          users: [
            {
              id: "u-site",
              email: "admin@example.com",
              role: "admin",
              site_role: "site_admin",
              created_at: "2024-01-01T00:00:00Z",
            },
            {
              id: "u-normal",
              email: "user@example.com",
              role: "user",
              site_role: "site_user",
              created_at: "2024-01-02T00:00:00Z",
            },
            {
              // The pair `agent_effective_role` (request_auth.py:64) refuses to
              // elevate: an untouched legacy column beside a deliberate downgrade.
              id: "u-legacy",
              email: "legacy@example.com",
              role: "admin",
              site_role: "site_user",
              created_at: "2024-01-03T00:00:00Z",
            },
          ],
        };
      }
      return { tenants: [], items: [] };
    },
  })),
}));

function renderAdminUsers() {
  return render(
    <MemoryRouter>
      <AdminUsers />
    </MemoryRouter>
  );
}

function setAuthUser(user: AuthUser | null) {
  authState.user = user;
}

const AGENTS_COL = "admin:usersColAgents";
const EMAIL_COL = "admin:usersColEmail";
const ROLE_COL = "admin:usersColRole";
const LOCK_KEY = "admin:usersSiteAdminLocked";

beforeEach(() => {
  setAuthUser(null);
});

describe("AdminUsers — agent-assign column visibility", () => {
  it("shows the Agents column for a site admin", async () => {
    setAuthUser({
      id: "a",
      email: "root@example.com",
      role: "admin",
      site_role: "site_admin",
    });
    renderAdminUsers();
    expect(
      await screen.findByRole("columnheader", { name: AGENTS_COL })
    ).toBeInTheDocument();
  });

  it("hides the Agents column for a delegated holder without agent.assign", async () => {
    setAuthUser({
      id: "a",
      email: "delegate@example.com",
      role: "user",
      site_role: "site_user",
      capabilities: ["user.manage"],
    });
    renderAdminUsers();
    await waitFor(() =>
      expect(
        screen.queryByRole("columnheader", { name: AGENTS_COL })
      ).toBeNull()
    );
    // Sanity: the list is still mounted, so other columns exist.
    expect(screen.getByRole("columnheader", { name: EMAIL_COL })).toBeInTheDocument();
  });

  it("shows the Agents column for a delegated holder of agent.assign", async () => {
    setAuthUser({
      id: "a",
      email: "delegate@example.com",
      role: "user",
      site_role: "site_user",
      capabilities: ["agent.assign"],
    });
    renderAdminUsers();
    expect(
      await screen.findByRole("columnheader", { name: AGENTS_COL })
    ).toBeInTheDocument();
  });
});

describe("AdminUsers — row editability lock", () => {
  it("locks the site-admin row for a delegated non-holder", async () => {
    setAuthUser({
      id: "a",
      email: "delegate@example.com",
      role: "user",
      site_role: "site_user",
      capabilities: ["user.manage"],
    });
    renderAdminUsers();
    expect(await screen.findByTitle(LOCK_KEY)).toBeInTheDocument();
  });

  it("does not lock any row for a site admin", async () => {
    setAuthUser({
      id: "a",
      email: "root@example.com",
      role: "admin",
      site_role: "site_admin",
    });
    renderAdminUsers();
    await waitFor(() => expect(screen.queryByTitle(LOCK_KEY)).toBeNull());
    expect(screen.getByRole("columnheader", { name: ROLE_COL })).toBeInTheDocument();
  });
});

describe("AdminUsers — the Role chip reads the canonical role", () => {
  function chipFor(email: string, label: string): HTMLElement {
    const row = screen.getByText(email).closest("tr");
    if (!row) throw new Error(`AdminUsers rendered no row for ${email}`);
    return within(row).getByText(label);
  }

  it("greens the account the server hands the instance to", async () => {
    setAuthUser({
      id: "a",
      email: "root@example.com",
      role: "admin",
      site_role: "site_admin",
    });
    renderAdminUsers();
    await screen.findByText("legacy@example.com");
    // `require_site_admin` (auth.py:422) reads `site_role`, so this is the row the
    // green chip is a claim about.
    expect(chipFor("admin@example.com", "site_admin").className).toContain("bg-success-subtle");
  });

  it("shows the legacy column without promoting it", async () => {
    setAuthUser({
      id: "a",
      email: "root@example.com",
      role: "admin",
      site_role: "site_admin",
    });
    renderAdminUsers();
    await screen.findByText("legacy@example.com");
    // `role: "admin"` beside `site_role: "site_user"` is the pair
    // `agent_effective_role` will not elevate: the value is still the account's
    // in-app rank, but it no longer reads as the top of the instance.
    const legacy = chipFor("legacy@example.com", "admin");
    expect(legacy.className).toContain("bg-accent-subtle");
    expect(legacy.className).not.toContain("bg-success-subtle");
    expect(chipFor("user@example.com", "user").className).toContain("bg-accent-subtle");
  });
});
