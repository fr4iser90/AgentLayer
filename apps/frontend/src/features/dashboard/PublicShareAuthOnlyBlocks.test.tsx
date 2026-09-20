import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPublicShareProvider } from "./DashboardPublicShareContext";
import { ShareWidgetBlockBody } from "./ShareWidgetBlock";
import { DashboardRefBlockBody } from "./DashboardRefBlock";
import { DashboardBlockTile } from "./DashboardBlocks";
import { apiFetch } from "../../lib/api";
import type { UiBlock } from "./types";

/**
 * Three block types read live data from a *signed-in* user: the friend share
 * preview, a cross-dashboard ref, and the scheduler list. None of them can
 * work for an anonymous public-share reader — the share token grants one
 * dashboard, not the owner's integrations — yet all three used to fire the
 * request anyway and render whatever came back. A 401 body of
 * `{"error":"unauthorized"}` went straight into the page.
 *
 * These pin the two halves of the fix:
 *   - in a public share the auth-only request is never issued at all;
 *   - the reader gets a stated reason instead of a response body.
 *
 * The control cases (no token) matter as much: the guard must not swallow
 * the ordinary authenticated path.
 */
type MockAuthState = { user: unknown; loading: boolean; accessToken: string };
const authState = vi.hoisted<MockAuthState>(() => ({
  user: { id: "owner-1" },
  loading: false,
  accessToken: "tok",
}));
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));

vi.mock("../../auth/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: tMock.t, i18n: { language: "en" } }),
  // The tile pulls in src/i18n/config, which registers this plugin at import.
  initReactI18next: { type: "3rdParty", init: () => {} },
}));
vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);

const AUTH_ONLY_CALLS = [
  "/v1/shares/preview/",
  "/blocks/",
  "/v1/user/scheduler-jobs",
];

function authOnlyCalls(): string[] {
  return api.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => AUTH_ONLY_CALLS.some((p) => u.includes(p)));
}

function unauthorized() {
  return {
    ok: false,
    status: 401,
    json: async () => ({ error: "unauthorized" }),
    text: async () => '{"error":"unauthorized"}',
  } as unknown as Response;
}

const SHARE_WIDGET: UiBlock = {
  id: "demo-share",
  type: "share_widget",
  props: { friendUserId: "friend-1", resourceType: "google_calendar" },
} as unknown as UiBlock;

const REF_BLOCK: UiBlock = {
  id: "demo-ref",
  type: "dashboard_ref",
  props: { sourceDashboardId: "src-1", sourceBlockId: "src-md" },
} as unknown as UiBlock;

const SCHEDULES_BLOCK: UiBlock = {
  id: "demo-schedules",
  type: "schedules",
  props: { scope: "dashboard" },
} as unknown as UiBlock;

beforeEach(() => {
  api.mockReset();
});

describe("public share blocks do not fire auth-only requests", () => {
  it("share widget skips the preview call and states why", async () => {
    api.mockImplementation(async () => unauthorized());
    render(
      <DashboardPublicShareProvider token="tok123" password={null}>
        <ShareWidgetBlockBody block={SHARE_WIDGET} />
      </DashboardPublicShareProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("dashboard:publicShareAuthOnlyBlock")).toBeInTheDocument(),
    );
    expect(authOnlyCalls()).toEqual([]);
  });

  it("dashboard ref skips the render call and states why", async () => {
    api.mockImplementation(async () => unauthorized());
    render(
      <DashboardPublicShareProvider token="tok123" password={null}>
        <DashboardRefBlockBody block={REF_BLOCK} readOnly />
      </DashboardPublicShareProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("dashboard:publicShareAuthOnlyBlock")).toBeInTheDocument(),
    );
    expect(authOnlyCalls()).toEqual([]);
  });

  it("schedules block skips the job list and states why", async () => {
    api.mockImplementation(async () => unauthorized());
    render(
      <DashboardPublicShareProvider token="tok123" password={null}>
        <DashboardBlockTile
          block={SCHEDULES_BLOCK}
          data={{}}
          setData={() => {}}
          readOnly
          dashboardId="dash-1"
        />
      </DashboardPublicShareProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("dashboard:publicShareAuthOnlyBlock")).toBeInTheDocument(),
    );
    expect(authOnlyCalls()).toEqual([]);
    // The "No data yet" placeholder must not stack under the stated reason.
    expect(screen.queryByText("admin:schedulesNoDataYet")).not.toBeInTheDocument();
  });
});

describe("authenticated (non-share) path still loads", () => {
  it("share widget still calls the preview endpoint without a share token", async () => {
    api.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ preview: { events: [{ summary: "Standup" }] } }),
      text: async () => JSON.stringify({ preview: { events: [{ summary: "Standup" }] } }),
    }) as unknown as Response);
    render(<ShareWidgetBlockBody block={SHARE_WIDGET} />);
    await waitFor(() =>
      expect(authOnlyCalls().some((u) => u.includes("/v1/shares/preview/"))).toBe(true),
    );
  });

  it("dashboard ref still calls the render endpoint without a share token", async () => {
    api.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ block: { id: "b", type: "markdown", props: {} }, data: {} }),
      text: async () => JSON.stringify({ block: { id: "b", type: "markdown", props: {} }, data: {} }),
    }) as unknown as Response);
    render(<DashboardRefBlockBody block={REF_BLOCK} readOnly />);
    await waitFor(() =>
      expect(authOnlyCalls().some((u) => u.includes("/render"))).toBe(true),
    );
  });

  it("schedules block still calls the job list without a share token", async () => {
    api.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, jobs: [], targets: [] }),
      text: async () => JSON.stringify({ ok: true, jobs: [], targets: [] }),
    }) as unknown as Response);
    render(
      <DashboardBlockTile
        block={SCHEDULES_BLOCK}
        data={{}}
        setData={() => {}}
        readOnly
        dashboardId="dash-1"
      />,
    );
    await waitFor(() =>
      expect(authOnlyCalls().some((u) => u.includes("/v1/user/scheduler-jobs"))).toBe(true),
    );
  });
});
