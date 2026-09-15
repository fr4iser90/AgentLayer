import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { AuthUser } from "../../auth/AuthContext";
import { apiFetch } from "../../lib/api";
import { AdminAgentSubmissions } from "./AdminAgentSubmissions";

// Stable auth identity across renders (see AdminUsers.test for rationale).
type MockAuthState = { user: AuthUser | null; loading: boolean };
const authState = vi.hoisted<MockAuthState>(() => ({ user: null, loading: false }));

// i18n: return the key so assertions are stable against locale changes. A single
// hoisted object keeps `t` referentially stable so dependent effects do not loop.
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => authState,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => tMock,
}));

vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(),
}));

const api = vi.mocked(apiFetch);

function submission(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "s1",
    agent_id: "research",
    title: "Research",
    description: "Does research.",
    system_prompt: "You are helpful.",
    agent_yaml: { id: "research" },
    target_dir: "plugins/agents/research",
    risk_level: "high",
    status: "pending",
    author_id: "user-1",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    materialize_error: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

/** Wire the mocked apiFetch to the three endpoints the page hits. */
function seed(rows: Record<string, unknown>[], preview?: Record<string, unknown>) {
  const calls: string[] = [];
  api.mockImplementation(
    // The mock returns a plain object; cast so it satisfies the real apiFetch
    // signature that `vi.mocked(apiFetch)` enforces on mockImplementation.
    ((url: unknown) => {
      const u = String(url);
      calls.push(u);
      if (u.includes("/review")) return { ok: true, json: async () => ({ ok: true }) };
      if (u.includes("/admin/agents/submissions")) {
        return { ok: true, json: async () => ({ submissions: rows }) };
      }
      return {
        ok: true,
        json: async () => ({
          ...(preview ?? rows[0]),
          yaml_text: "id: research\n",
          tool_warnings: ["ghost_tool"],
        }),
      };
    }) as unknown as typeof apiFetch,
  );
  return calls;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminAgentSubmissions />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  authState.user = { id: "a", email: "root@example.com", role: "admin", site_role: "site_admin" };
  api.mockReset();
});

describe("AdminAgentSubmissions", () => {
  it("lists submissions, badges risk/status, and previews the selected row", async () => {
    seed([submission()]);
    renderPage();
    expect(await screen.findByText("admin:agentSubmissionsTitle")).toBeInTheDocument();
    // The title/risk/status render in both the list row and the detail panel.
    expect(screen.getAllByText("Research").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("admin:agentSubmissionsRiskHigh").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("admin:agentSubmissionsStatusPending").length).toBeGreaterThanOrEqual(1);
    // Selecting a row loads the preview (yaml + tool warnings).
    await waitFor(() => expect(screen.getByText("id: research")).toBeInTheDocument());
    expect(screen.getByText("ghost_tool")).toBeInTheDocument();
  });

  it("shows the empty state when nothing matches the filter", async () => {
    seed([]);
    renderPage();
    expect(await screen.findByText("admin:agentSubmissionsNone")).toBeInTheDocument();
    expect(screen.queryByText("Research")).not.toBeInTheDocument();
  });

  it("records an approve review through the confirm dialog", async () => {
    seed([submission({ status: "pending" })]);
    renderPage();
    const APPROVE = "admin:agentSubmissionsApprove";
    // Wait for the auto-selected detail panel to expose its approve control(s).
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: APPROVE }).length).toBeGreaterThanOrEqual(1),
    );
    // Click the first approve; the confirm dialog exposes a second approve button.
    fireEvent.click(screen.getAllByRole("button", { name: APPROVE })[0]);
    fireEvent.click(screen.getAllByRole("button", { name: APPROVE })[1]);
    expect(await screen.findByText("admin:agentSubmissionsReviewRecorded")).toBeInTheDocument();
    const urls = api.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("/admin/agents/submissions/") && u.includes("/review"))).toBe(true);
  });
});
