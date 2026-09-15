import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
