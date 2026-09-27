import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MySchedulesPage } from "./MySchedulesPage";

// One component now answers for `/schedules` and `/admin/schedules`, so the
// scope prop is the only thing that decides which endpoint family the page
// talks to and who may archive a row. A silent `scope` regression would hand a
// self-service user the company's job list while still looking like their own
// page — hence these pin the request URLs, not the markup.
const authState = vi.hoisted(() => ({
  user: null as null | { role?: string; site_role?: string },
  loading: false,
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const backend = vi.hoisted(() => ({
  calls: [] as string[],
  jobs: [] as unknown[],
  targets: [] as unknown[],
}));

vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(async (url: string) => {
    backend.calls.push(url);
    if (url.startsWith("/v1/user/scheduler-jobs/execution-targets")) {
      return { ok: true, json: async () => ({ ok: true, targets: backend.targets }) };
    }
    if (url.startsWith("/v1/user/scheduler-job-presets")) {
      return { ok: true, json: async () => ({ ok: true, presets: [] }) };
    }
    if (url.startsWith("/v1/workspaces")) {
      return { ok: true, json: async () => ({ ok: true, workspaces: [] }) };
    }
    return { ok: true, json: async () => ({ ok: true, jobs: backend.jobs }) };
  }),
}));

const job = (over: Record<string, unknown> = {}) => ({
  id: "job-1",
  dashboard_id: null,
  execution_target: "coding",
  title: "Nightly docs",
  interval_minutes: 1440,
  enabled: true,
  last_run_at: null,
  created_at: "2026-01-01T00:00:00Z",
  instructions: "Regenerate the docs.",
  ...over,
});

/** Every catalog row is `general`; `coding` is the registry's admin-only agent. */
const catalog = () => [
  { value: "general", label: "General", agent_id: "general" },
  { value: "coding", label: "Coding", agent_id: "coding", requires_workspace: true, min_role: "admin" },
];

const askedFor = (prefix: string) => backend.calls.filter((u) => u.startsWith(prefix));

beforeEach(() => {
  backend.calls = [];
  backend.jobs = [job()];
  backend.targets = catalog();
  authState.user = { role: "user", site_role: "site_user" };
});

describe("MySchedulesPage scope switch", () => {
  it("reads its own jobs on the default scope and never the admin family", async () => {
    render(<MySchedulesPage />);

    await waitFor(() => expect(askedFor("/v1/user/scheduler-jobs?limit=200")).toHaveLength(1));
    expect(askedFor("/v1/admin/")).toEqual([]);
    expect(screen.getByRole("heading", { name: "common:nav.schedules" })).toBeInTheDocument();
    expect(screen.queryByText("admin:schedulesScope")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "admin:schedulesArchive" })).not.toBeInTheDocument();
  });

  it("reads the company list, its filters and the archive control on the admin scope", async () => {
    backend.jobs = [job({ deleted_at: "2026-02-01T00:00:00Z" })];
    render(<MySchedulesPage scope="admin" />);

    await waitFor(() => expect(askedFor("/v1/admin/scheduler-jobs?limit=200")).toHaveLength(1));
    expect(askedFor("/v1/user/scheduler-jobs?")).toEqual([]);
    expect(screen.getByRole("heading", { name: "admin:schedulesTitle" })).toBeInTheDocument();
    expect(screen.getByText("admin:schedulesScope")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "admin:schedulesUnarchive" })).toBeInTheDocument();
    expect(screen.getByText("admin:schedulesArchivedLabel")).toBeInTheDocument();
    // Both scopes pick presets off the one directory the backend keeps.
    expect(askedFor("/v1/user/scheduler-job-presets")).toHaveLength(1);
  });

  it("re-lists with the filter the admin just changed", async () => {
    render(<MySchedulesPage scope="admin" />);
    await waitFor(() => expect(askedFor("/v1/admin/scheduler-jobs?")).toHaveLength(1));

    fireEvent.click(screen.getByRole("checkbox"));

    await waitFor(() =>
      expect(askedFor("/v1/admin/scheduler-jobs?").at(-1)).toContain("include_archived=true")
    );
  });

  it("keeps the user list out of reach of the admin filters", async () => {
    render(<MySchedulesPage />);
    await waitFor(() => expect(askedFor("/v1/user/scheduler-jobs?limit=200")).toHaveLength(1));
    // No filter card means no second request: the page asks once.
    expect(askedFor("/v1/user/scheduler-jobs?")).toHaveLength(1);
  });
});

describe("MySchedulesPage target catalog gate", () => {
  const targetOptions = async () => {
    render(<MySchedulesPage />);
    await waitFor(() => expect(askedFor("/v1/user/scheduler-jobs/execution-targets")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "admin:schedulesCreate" }));
    return screen.getAllByRole("option").map((o) => o.textContent);
  };

  it("hides an admin target from a plain user", async () => {
    expect(await targetOptions()).toEqual(["—", "General"]);
  });

  it("hides it from a legacy admin row that the site flag says is a user", async () => {
    authState.user = { role: "admin", site_role: "site_user" };
    expect(await targetOptions()).toEqual(["—", "General"]);
  });

  it("shows it to a site admin", async () => {
    authState.user = { role: "user", site_role: "site_admin" };
    expect(await targetOptions()).toEqual(["—", "General", "Coding"]);
  });

  it("still honours the legacy column while the site flag is unset", async () => {
    authState.user = { role: "admin" };
    expect(await targetOptions()).toEqual(["—", "General", "Coding"]);
  });
});