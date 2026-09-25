import { describe, expect, it } from "vitest";
import {
  canAssignAgents,
  canManageWorkspaceGrants,
  canReachOrgSurface,
  isSiteAdmin,
  isTargetEditable,
  normalizeCapabilities,
  visibleColSpan,
} from "./accessGating";
import type { AccessActor } from "./accessGating";

const siteAdmin: AccessActor = { site_role: "site_admin" };
const delegated: AccessActor = { site_role: "site_user" };
const delegatedWithAgentAssign: AccessActor = {
  site_role: "site_user",
  capabilities: ["agent.assign"],
};

describe("normalizeCapabilities", () => {
  it("lowercases and trims granted slugs", () => {
    expect(
      normalizeCapabilities({ capabilities: [" Agent.Assign ", "User.Manage"] })
    ).toEqual(new Set(["agent.assign", "user.manage"]));
  });

  it("drops blanks and duplicates", () => {
    expect(
      normalizeCapabilities({
        capabilities: ["", "  ", "agent.assign", "agent.assign"],
      })
    ).toEqual(new Set(["agent.assign"]));
  });

  it("treats missing capabilities as empty", () => {
    expect(normalizeCapabilities({ site_role: "site_user" })).toEqual(new Set());
    expect(normalizeCapabilities(undefined)).toEqual(new Set());
    expect(normalizeCapabilities(null)).toEqual(new Set());
  });
});

describe("canAssignAgents", () => {
  it("true for a site admin regardless of capabilities", () => {
    expect(canAssignAgents(siteAdmin)).toBe(true);
    expect(canAssignAgents({ site_role: "site_admin", capabilities: [] })).toBe(
      true
    );
  });

  it("true for a delegated holder of agent.assign (case-insensitive)", () => {
    expect(canAssignAgents(delegatedWithAgentAssign)).toBe(true);
    expect(
      canAssignAgents({
        site_role: "site_user",
        capabilities: ["AGENT.ASSIGN"],
      })
    ).toBe(true);
  });

  it("false for a delegated holder without agent.assign", () => {
    expect(canAssignAgents(delegated)).toBe(false);
    expect(
      canAssignAgents({
        site_role: "site_user",
        capabilities: ["user.manage"],
      })
    ).toBe(false);
    expect(canAssignAgents(undefined)).toBe(false);
  });
});

describe("canManageWorkspaceGrants", () => {
  it("true for a site admin regardless of capabilities", () => {
    expect(canManageWorkspaceGrants(siteAdmin)).toBe(true);
    expect(canManageWorkspaceGrants({ site_role: "site_admin", capabilities: [] })).toBe(true);
  });

  it("true for a delegated holder of workspace.manage, case-insensitive", () => {
    expect(
      canManageWorkspaceGrants({ site_role: "site_user", capabilities: ["workspace.manage"] })
    ).toBe(true);
    expect(
      canManageWorkspaceGrants({ site_role: "site_user", capabilities: ["WORKSPACE.MANAGE"] })
    ).toBe(true);
  });

  it("false without workspace.manage — a tenant role alone is not a capability", () => {
    expect(canManageWorkspaceGrants(delegated)).toBe(false);
    expect(
      canManageWorkspaceGrants({ site_role: "site_user", capabilities: ["dashboard.manage"] })
    ).toBe(false);
    expect(canManageWorkspaceGrants(undefined)).toBe(false);
  });
});

describe("isTargetEditable", () => {
  it("site admin may edit everyone", () => {
    expect(isTargetEditable(siteAdmin, { site_role: "site_admin" })).toBe(true);
    expect(isTargetEditable(siteAdmin, { site_role: "site_user" })).toBe(true);
  });

  it("delegated holder may edit any non-site-admin user", () => {
    expect(isTargetEditable(delegated, { site_role: "site_user" })).toBe(true);
    expect(isTargetEditable(delegated, { site_role: null })).toBe(true);
  });

  it("delegated holder may NOT edit a site admin (mirrors the backend PATCH boundary)", () => {
    expect(isTargetEditable(delegated, { site_role: "site_admin" })).toBe(false);
  });

  it("defaults to editable when the target is unknown", () => {
    expect(isTargetEditable(delegated)).toBe(true);
    expect(isTargetEditable(undefined, undefined)).toBe(true);
  });
});

describe("visibleColSpan", () => {
  it("base span 15 in multi-tenant mode", () => {
    expect(visibleColSpan(delegatedWithAgentAssign, false)).toBe(15);
  });

  it("base span 14 in agent_system mode (no Tenant column)", () => {
    expect(visibleColSpan(delegatedWithAgentAssign, true)).toBe(14);
  });

  it("shrinks by one column when the actor cannot see the agents column", () => {
    expect(visibleColSpan(delegated, false)).toBe(14);
    expect(visibleColSpan(delegated, true)).toBe(13);
  });

  it("full span for a site admin or delegated holder", () => {
    expect(visibleColSpan(siteAdmin, false)).toBe(15);
    expect(visibleColSpan(delegatedWithAgentAssign, true)).toBe(14);
  });
});

/**
 * The two predicates that decide whether a surface door is drawn. They used to
 * be inline in the components that asked them — `RequireSiteAdmin` and the
 * avatar menu each had a copy — and the menu's copy of the org question left out
 * everyone who was not a tenant owner or admin, so a knowledge editor could open
 * `/org/knowledge` and see no link to it anywhere.
 *
 * Pinned here rather than in a render test because the question is data, not
 * layout: which field, compared with what.
 */
describe("isSiteAdmin", () => {
  it("reads the authoritative site_role", () => {
    expect(isSiteAdmin({ site_role: "site_admin" })).toBe(true);
    expect(isSiteAdmin({ site_role: "site_user" })).toBe(false);
  });

  it("still reads the legacy role, case and padding aside", () => {
    expect(isSiteAdmin({ role: "admin" })).toBe(true);
    expect(isSiteAdmin({ role: " Admin " })).toBe(true);
    expect(isSiteAdmin({ role: "user" })).toBe(false);
  });

  it("is not a tenant question", () => {
    expect(isSiteAdmin({ membership_role: "tenant_owner" })).toBe(false);
    expect(isSiteAdmin(undefined)).toBe(false);
    expect(isSiteAdmin(null)).toBe(false);
  });
});

describe("canReachOrgSurface", () => {
  it("true for the membership roles that administer the company", () => {
    expect(canReachOrgSurface({ membership_role: "tenant_owner" })).toBe(true);
    expect(canReachOrgSurface({ membership_role: "tenant_admin" })).toBe(true);
  });

  it("true for a content editor and a delegated grants holder", () => {
    // The two halves the avatar menu never knew about.
    expect(
      canReachOrgSurface({ profession_policy: { can_edit_content: true } })
    ).toBe(true);
    expect(
      canReachOrgSurface({ site_role: "site_user", capabilities: ["workspace.manage"] })
    ).toBe(true);
  });

  it("false for a plain member, which is what hid the door honestly", () => {
    expect(canReachOrgSurface({ membership_role: "member" })).toBe(false);
    expect(
      canReachOrgSurface({ profession_policy: { can_edit_content: false } })
    ).toBe(false);
    expect(canReachOrgSurface(undefined)).toBe(false);
  });
});
