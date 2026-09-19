import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { AuthUser } from "../../auth/AuthContext";
import { OrgGrantsPage } from "./OrgGrantsPage";
import { fetchWorkspacesApi } from "../../lib/workspacesApi";
import {
  fetchEntityGrantsApi,
  replaceEntityGrantsApi,
} from "../../lib/entityGrantsApi";

/**
 * Stable identities across renders. `load` is a useCallback keyed on
 * `[auth, t]`; a fresh object from `useAuth` or a fresh `t` would make it a
 * new callback every render and re-fire the load effect forever — the page
 * would spin with no output instead of failing.
 */
type MockAuthState = { user: AuthUser | null; loading: boolean; accessToken: string };
const authState = vi.hoisted<MockAuthState>(() => ({
  user: null,
  loading: false,
  accessToken: "tok",
}));
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));

vi.mock("../../auth/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("react-i18next", () => ({ useTranslation: () => tMock }));
vi.mock("../../lib/workspacesApi", () => ({ fetchWorkspacesApi: vi.fn() }));

// Keep the pure mapping helpers real — the test should exercise the actual
// grant-row interpretation, not a stub of it.
vi.mock("../../lib/entityGrantsApi", async (importOriginal) => {
  const real = await importOriginal<typeof import("../../lib/entityGrantsApi")>();
  return {
    ...real,
    fetchEntityGrantsApi: vi.fn(),
    replaceEntityGrantsApi: vi.fn(),
  };
});

const listWorkspaces = vi.mocked(fetchWorkspacesApi);
const getGrants = vi.mocked(fetchEntityGrantsApi);
const putGrants = vi.mocked(replaceEntityGrantsApi);

function ws(id: string, name: string, visibility: "private" | "tenant" = "tenant") {
  return {
    id,
    owner_user_id: "owner-1",
    name,
    path: `/x/${name}`,
    source: "git",
    git_url: null,
    git_branch: "main",
    access_role: "owner" as const,
    created_at: null,
    updated_at: null,
    tenant_id: 7,
    visibility,
  };
}

function grantsAdminRowOnly() {
  // The redundant shape: a row naming tenant_admin, which changes nothing.
  return {
    entity_type: "workspace",
    entity_id: "w1",
    tenant_id: 7,
    grants: [{ min_role: "tenant_admin", access: "manage" as const, created_by: null, created_at: null }],
  };
}

function tenantAdminUser() {
  return {
    id: "u1",
    email: "a@b.c",
    deployment_mode: "multi_tenant",
    site_role: "site_user",
    membership_role: "tenant_admin",
    capabilities: ["workspace.manage"],
  } as unknown as AuthUser;
}

beforeEach(() => {
  vi.clearAllMocks();
  authState.user = tenantAdminUser();
  listWorkspaces.mockResolvedValue({ workspaces: [ws("w1", "api"), ws("w2", "web")] });
  getGrants.mockImplementation(async (_auth, _type, id) => ({
    entity_type: "workspace",
    entity_id: id,
    tenant_id: 7,
    grants: [{ min_role: "tenant_member", access: "view" as const, created_by: null, created_at: null }],
  }));
  putGrants.mockResolvedValue(undefined);
});

function renderPage() {
  return render(
    <MemoryRouter>
      <OrgGrantsPage />
    </MemoryRouter>
  );
}

it("lists the company workspaces the caller can share", async () => {
  renderPage();
  await waitFor(() => expect(screen.getByText("api")).toBeTruthy());
  expect(screen.getByText("web")).toBeTruthy();
  expect(listWorkspaces).toHaveBeenCalledWith(expect.anything(), "company");
});

it("shows the current member access level read from the tenant_member row", async () => {
  renderPage();
  const select = (await screen.findByLabelText(/api/)) as HTMLSelectElement;
  expect(select.value).toBe("view");
});

it("ignores grant rows naming tenant_admin when reading the member level", async () => {
  getGrants.mockResolvedValue(grantsAdminRowOnly());
  renderPage();
  const select = (await screen.findByLabelText(/api/)) as HTMLSelectElement;
  // A tenant_admin row must not read as "members have access".
  expect(select.value).toBe("");
});

it("PUTs the chosen level for the tenant_member role", async () => {
  renderPage();
  const select = (await screen.findByLabelText(/api/)) as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "edit" } });
  await waitFor(() => expect(putGrants).toHaveBeenCalled());
  const [auth, type, id, grants] = putGrants.mock.calls[0];
  expect(type).toBe("workspace");
  expect(id).toBe("w1");
  expect(grants).toEqual([{ min_role: "tenant_member", access: "edit" }]);
  expect(auth).toBe(authState);
});

it("revokes by sending an empty grant set rather than a row with a blank level", async () => {
  renderPage();
  const select = (await screen.findByLabelText(/api/)) as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "" } });
  await waitFor(() => expect(putGrants).toHaveBeenCalled());
  expect(putGrants.mock.calls[0][3]).toEqual([]);
});

it("disables the control and warns for a workspace that is not company-visible", async () => {
  listWorkspaces.mockResolvedValue({
    workspaces: [ws("w1", "secret-repo", "private")],
  });
  renderPage();
  const select = (await screen.findByLabelText(/secret-repo/)) as HTMLSelectElement;
  expect(select.disabled).toBe(true);
  expect(screen.getByText("org:grantsInertWhilePrivate")).toBeTruthy();
});

it("surfaces a per-row failure without taking the whole list down", async () => {
  getGrants.mockImplementation(async (_auth, _type, id) => {
    if (id === "w2") throw new Error("grant read exploded");
    return { entity_type: "workspace", entity_id: id, tenant_id: 7, grants: [] };
  });
  renderPage();
  await waitFor(() => expect(screen.getByText("grant read exploded")).toBeTruthy());
  // The other row still rendered.
  expect(screen.getByText("api")).toBeTruthy();
});

it("shows the empty state when nothing is company-visible", async () => {
  listWorkspaces.mockResolvedValue({ workspaces: [] });
  renderPage();
  await waitFor(() => expect(screen.getByText("org:grantsEmpty")).toBeTruthy());
});

it("does not offer the screen outside the org surface", async () => {
  authState.user = {
    id: "u1",
    email: "a@b.c",
    deployment_mode: "single_user",
    site_role: "site_user",
    membership_role: "tenant_member",
    capabilities: [],
  } as unknown as AuthUser;
  renderPage();
  await waitFor(() => expect(screen.getByText("org:grantsNoOrg")).toBeTruthy());
  expect(listWorkspaces).not.toHaveBeenCalled();
});
