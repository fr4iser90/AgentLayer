/**
 * The Mine / Company scope switch on the projects list.
 *
 * The company tab is the only place a plain member reaches a workspace they do
 * not own, so two things are worth pinning down:
 *
 * 1. the tab follows the org-surface predicate — it must not appear in
 *    ``single_user``, where tenant chrome is supposed to be absent entirely;
 * 2. the scope travels to the API rather than filtering the loaded list
 *    client-side. A local filter would render rows the backend never intended
 *    to hand over, and would silently break the moment the two lists differ.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { AuthUser } from "../auth/AuthContext";
import type { WorkspaceApiRecord } from "../lib/api";
import { ProjectsPage } from "./ProjectsPage";

type Scope = "mine" | "company";

const state = vi.hoisted(() => ({
  scopes: [] as string[],
  mine: [] as unknown[],
  company: [] as unknown[],
  companyTenantId: null as number | null,
}));

// Stable identity on purpose. `reload` is a useCallback keyed on the auth value;
// a fresh object per call would make it a new callback every render, re-firing
// the load effect forever.
const authStub = vi.hoisted(() => ({
  user: null as unknown,
  accessToken: "tok",
  refresh: async () => null,
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => authStub,
}));

vi.mock("../lib/workspacesApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/workspacesApi")>();
  return {
    ...actual,
    fetchWorkspacesApi: vi.fn(async (_auth: unknown, scope: Scope) => {
      state.scopes.push(scope);
      if (scope === "company") {
        return { workspaces: state.company, scope: "company", tenant_id: state.companyTenantId };
      }
      return { workspaces: state.mine, scope: "mine", tenant_id: null };
    }),
    deleteWorkspaceApi: vi.fn(async () => {}),
  };
});

vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(async () => ({ ok: true, json: async () => ({ entries: [] }) })),
}));

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

function userIn(mode: string): AuthUser {
  return {
    id: "u1",
    email: "member@example.com",
    role: "user",
    site_role: "site_member",
    capabilities: [],
    tenant_id: 1,
    membership_role: "tenant_member",
    deployment_mode: mode,
  } as AuthUser;
}

function ws(name: string, visibility: "private" | "tenant"): WorkspaceApiRecord {
  return {
    id: `w-${name}`,
    owner_user_id: "u1",
    name,
    path: `/workspaces/${name}`,
    source: "git",
    git_url: null,
    git_branch: "main",
    access_role: "owner",
    created_at: null,
    updated_at: null,
    visibility,
  } as WorkspaceApiRecord;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  state.scopes.length = 0;
  state.mine = [];
  state.company = [];
  state.companyTenantId = 1;
  authStub.user = userIn("multi_tenant");
});

describe("projects list scope switch", () => {
  it("offers both scopes when the deployment has an org surface", async () => {
    renderPage();
    await waitFor(() => expect(state.scopes).toEqual(["mine"]));
    expect(screen.getByRole("tab", { name: "workspace:projectsScopeMine" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "workspace:projectsScopeCompany" })).toBeTruthy();
  });

  it("does not offer the company scope in single_user", async () => {
    authStub.user = userIn("single_user");
    renderPage();
    await waitFor(() => expect(state.scopes).toEqual(["mine"]));
    expect(screen.queryByRole("tab", { name: "workspace:projectsScopeCompany" })).toBeNull();
    expect(screen.getByText("workspace:projectsListTitle")).toBeTruthy();
  });

  it("asks the backend for the company list instead of filtering locally", async () => {
    state.company = [ws("shared-repo", "tenant")];
    renderPage();
    await waitFor(() => expect(state.scopes).toEqual(["mine"]));

    fireEvent.click(screen.getByRole("tab", { name: "workspace:projectsScopeCompany" }));

    await waitFor(() => expect(state.scopes).toEqual(["mine", "company"]));
    // Role-scoped: the selected workspace's name also appears in the detail
    // header, so a bare text query would match both.
    expect(screen.getAllByRole("button", { name: /shared-repo/ })).toHaveLength(1);
  });

  it("says the caller has no company rather than showing an empty list", async () => {
    state.companyTenantId = null;
    renderPage();
    await waitFor(() => expect(state.scopes).toEqual(["mine"]));

    fireEvent.click(screen.getByRole("tab", { name: "workspace:projectsScopeCompany" }));

    await waitFor(() => expect(screen.getByText("workspace:projectsCompanyNoTenant")).toBeTruthy());
    expect(screen.queryByText("workspace:projectsEmpty")).toBeNull();
  });

  it("marks only the company-visible entries in the private list", async () => {
    state.mine = [ws("shared-one", "tenant"), ws("private-one", "private")];
    renderPage();
    await waitFor(() => expect(screen.getAllByRole("button", { name: /shared-one/ })).toHaveLength(1));
    expect(screen.getAllByRole("button", { name: /private-one/ })).toHaveLength(1);
    expect(screen.getAllByText("workspace:visibilityCompanyTag")).toHaveLength(1);
  });
});
