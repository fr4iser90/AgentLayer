import { describe, expect, it } from "vitest";
import {
  canAssignAgents,
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
