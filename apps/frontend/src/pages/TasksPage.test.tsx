import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TasksPage } from "./TasksPage";

// The loading state exists to be replaced, and the point of replacing a text
// line with a skeleton is the height it reserves. So this file pins both halves:
// the placeholder is announced while it is up, it reserves three rows of the
// measured height, and it is gone once the rows are. A regression to
// `<p>Loading</p>` fails the height assertion, not just an aesthetic review.
const authState = vi.hoisted(() => ({ user: null, loading: false }));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// `gate` hands the test the resolver for the in-flight task request, so the
// loading branch can be observed before the data is allowed to land.
const gateway = vi.hoisted(() => ({
  tasks: [] as unknown[],
  release: null as null | ((value: { tasks: unknown[] }) => void),
}));

vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(async (url: string) => {
    if (url.startsWith("/v1/workspaces")) {
      return { ok: true, json: async () => ({ workspaces: [] }) };
    }
    const body = await new Promise<{ tasks: unknown[] }>((resolve) => {
      gateway.release = resolve;
    });
    return { ok: true, json: async () => body };
  }),
}));

const task = {
  id: "t-1",
  scope: "global" as const,
  goal: "Reproduce the layout shift",
  status: "open",
  priority: "normal",
};

beforeEach(() => {
  gateway.tasks = [];
  gateway.release = null;
});

describe("TasksPage loading state", () => {
  it("announces the placeholder and reserves three task rows", () => {
    render(
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("tasks:loading");

    const rows = document.querySelector("[data-skeleton-rows]");
    expect(rows).not.toBeNull();
    // 3 rows x the measured 98 px (84 px row + 8 px gap + the border pair).
    expect(rows).toHaveStyle({ minHeight: "294px" });
  });

  it("drops the placeholder when the rows arrive", async () => {
    render(
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>
    );
    expect(screen.getByRole("status")).toBeInTheDocument();

    gateway.release?.({ tasks: [task] });

    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(screen.getByText("Reproduce the layout shift")).toBeInTheDocument();
    expect(document.querySelector("[data-skeleton-rows]")).toBeNull();
  });
});