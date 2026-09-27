import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AuthUser } from "../../auth/AuthContext";
import { OrgContentCms } from "./OrgContentCms";

/**
 * Who the CMS lets press publish.
 *
 * The two buttons below the editor are the only thing between an account and a
 * published note, and the endpoint they aim at is picked by deployment mode:
 * `apiBase` sends an org-surface session to `/v1/org/tenant-content`, which asks a
 * membership plus `content.review` / `content.publish`, and everyone else to
 * `/v1/admin/tenant-content`, which asks `require_site_admin` — `site_role` and
 * nothing else (auth.py:422). Both flags used to OR in the legacy `users.role`
 * column on top, which is the column `agent_effective_role` (request_auth.py:64)
 * will not let elevate: a `role: "admin"` paired with `site_role: "site_user"` got
 * the buttons and a rejection on every click.
 *
 * `t` returns the key, so these assertions are stable against locale text.
 */

const authState = vi.hoisted(() => ({ user: null as AuthUser | null, loading: false }));

vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => authState
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } })
}));

const APPROVED_NOTE = {
  id: "n-approved",
  slug: "approved-note",
  title: "Approved note",
  body_md: "Ready to go out.",
  status: "approved",
  version: 3
};

const requestedUrls = vi.hoisted(() => [] as string[]);

vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(async (url: string) => {
    requestedUrls.push(url);
    if (url.endsWith("/review-queue")) return { ok: true, json: async () => ({ items: [] }) };
    if (url.endsWith("/versions")) return { ok: true, json: async () => ({ items: [] }) };
    return { ok: true, json: async () => ({ items: [APPROVED_NOTE] }) };
  })
}));

const PUBLISH = "org:cmsPublish";
const NEEDS_APPROVER = "org:cmsPublishRequiresApprover";
// The queue tab renders `t(key) (count)`, so its text is never the bare key: an
// exact-string query would report "no review tab" for the wrong reason.
const REVIEW_FILTER = /^org:cmsFilterReview/;
const EDIT_HEADING = "org:cmsEditNote";

/** Select the stored note so the editor shows it in the `approved` state. */
async function openApprovedNote() {
  fireEvent.click(await screen.findByText(APPROVED_NOTE.title));
  await screen.findByText(EDIT_HEADING);
}

const asUser = (partial: Record<string, unknown>) =>
  ({ id: "u-1", email: "u@example.com", ...partial }) as AuthUser;

/** Multi-tenant session: the CMS talks to the org surface. */
const MULTITENANT = {
  deployment_mode: "multi_tenant",
  tenant_id: 7,
  capabilities: []
};

beforeEach(() => {
  authState.user = null;
  authState.loading = false;
  requestedUrls.length = 0;
});

describe("the legacy role column opens nothing", () => {
  it("hides publish and review from an admin column paired with site_user", async () => {
    authState.user = asUser({
      ...MULTITENANT,
      role: "admin",
      site_role: "site_user",
      membership_role: null
    });
    render(<OrgContentCms />);
    await screen.findByText(APPROVED_NOTE.title);
    expect(screen.queryByText(REVIEW_FILTER)).toBeNull();
    await openApprovedNote();
    expect(screen.queryByText(PUBLISH)).toBeNull();
    expect(screen.getByText(NEEDS_APPROVER)).toBeInTheDocument();
  });

  it("keeps hiding them when the same account is a plain tenant member", async () => {
    // A membership without the review/publish capability is the common shape:
    // `require_tenant_member` lets the note list load, the policy still says no.
    authState.user = asUser({
      ...MULTITENANT,
      role: "admin",
      site_role: "site_user",
      membership_role: "tenant_member",
      profession_policy: { can_edit_content: true, can_review_content: false, can_publish_content: false }
    });
    render(<OrgContentCms />);
    await openApprovedNote();
    expect(screen.queryByText(PUBLISH)).toBeNull();
    expect(screen.queryByText(REVIEW_FILTER)).toBeNull();
  });

  it("takes the chip off the platform operator's own column too when the admin column is all it has", async () => {
    // Without an org surface the admin endpoint answers only `site_role`, so an
    // `admin` here would watch its publish fail on every click.
    authState.user = asUser({ deployment_mode: "agent_system", role: "admin", site_role: "site_user" });
    render(<OrgContentCms />);
    await openApprovedNote();
    expect(screen.queryByText(PUBLISH)).toBeNull();
  });
});

describe("what the endpoints actually serve still publishes", () => {
  it("hands publish to the profession the org policy says may publish", async () => {
    authState.user = asUser({
      ...MULTITENANT,
      role: "user",
      site_role: "site_user",
      membership_role: "tenant_member",
      profession_policy: { can_review_content: true, can_publish_content: true }
    });
    render(<OrgContentCms />);
    await openApprovedNote();
    expect(screen.getByText(PUBLISH)).toBeInTheDocument();
    expect(screen.getByText(REVIEW_FILTER)).toBeInTheDocument();
    expect(requestedUrls).toContain("/v1/org/tenant-content/review-queue");
  });

  it("keeps the buttons for a tenant admin whose policy could not be resolved", async () => {
    // `profession_policy` is served with a membership and dropped when the policy
    // read throws (auth_api.py:337); the membership role still answers, and the
    // server grants both slugs to that role, so nothing may disappear here.
    authState.user = asUser({
      ...MULTITENANT,
      role: "user",
      site_role: "site_user",
      membership_role: "tenant_admin"
    });
    render(<OrgContentCms />);
    await openApprovedNote();
    expect(screen.getByText(PUBLISH)).toBeInTheDocument();
  });

  it("hands publish to the platform operator without an org surface", async () => {
    authState.user = asUser({ deployment_mode: "agent_system", role: "admin", site_role: "site_admin" });
    render(<OrgContentCms />);
    await openApprovedNote();
    expect(screen.getByText(PUBLISH)).toBeInTheDocument();
    expect(requestedUrls).toContain("/v1/admin/tenant-content");
  });
});

describe("an identity that has not arrived yet", () => {
  it("shows neither publish nor the review queue while the session loads", async () => {
    authState.user = null;
    render(<OrgContentCms />);
    // The list is loaded unconditionally, so the queue is the honest signal: it is
    // only asked for once something says the caller may review.
    await waitFor(() => expect(requestedUrls.length).toBeGreaterThan(0));
    expect(requestedUrls.some((u) => u.endsWith("/review-queue"))).toBe(false);
    expect(screen.queryByText(PUBLISH)).toBeNull();
  });
});