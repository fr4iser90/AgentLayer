import { describe, expect, it } from "vitest";
import {
  deploymentMode,
  hasOrgSurface,
  isSingleUser,
  type DeploymentMode,
} from "./deploymentMode";
import type { AuthUser } from "./AuthContext";

function user(mode?: unknown): AuthUser {
  return { deployment_mode: mode } as AuthUser;
}

const MODES: readonly DeploymentMode[] = ["single_user", "agent_system", "multi_tenant"];

describe("deploymentMode", () => {
  it("narrows each known mode", () => {
    for (const mode of MODES) {
      expect(deploymentMode(user(mode))).toBe(mode);
    }
  });

  it("tolerates case and surrounding whitespace", () => {
    expect(deploymentMode(user("  SINGLE_USER "))).toBe("single_user");
    expect(deploymentMode(user("Agent_System"))).toBe("agent_system");
  });

  it("falls back to multi_tenant for unknown or missing values", () => {
    expect(deploymentMode(user("solo"))).toBe("multi_tenant");
    expect(deploymentMode(user(undefined))).toBe("multi_tenant");
    expect(deploymentMode(user(null))).toBe("multi_tenant");
    expect(deploymentMode(null)).toBe("multi_tenant");
    expect(deploymentMode(undefined)).toBe("multi_tenant");
  });
});

describe("hasOrgSurface", () => {
  it("is true only in multi_tenant", () => {
    expect(hasOrgSurface(user("multi_tenant"))).toBe(true);
    expect(hasOrgSurface(user("agent_system"))).toBe(false);
    expect(hasOrgSurface(user("single_user"))).toBe(false);
  });

  it("treats an unread mode as having the org surface", () => {
    expect(hasOrgSurface(user("solo"))).toBe(true);
    expect(hasOrgSurface(undefined)).toBe(true);
  });
});

describe("isSingleUser", () => {
  it("is true only in single_user", () => {
    expect(isSingleUser(user("single_user"))).toBe(true);
    expect(isSingleUser(user("agent_system"))).toBe(false);
    expect(isSingleUser(user("multi_tenant"))).toBe(false);
  });
});

describe("the three modes stay separate", () => {
  it("no mode is both single-user and org-surfaced", () => {
    for (const mode of [...MODES, "solo", "", undefined, null]) {
      expect(hasOrgSurface(user(mode)) && isSingleUser(user(mode))).toBe(false);
    }
  });

  it("single_user is neither of the two modes it could be confused with", () => {
    // The old guards were `=== "agent_system"` / `!== "agent_system"`. A third
    // value read through either of those silently inherits a neighbour's chrome.
    const single = user("single_user");
    expect(isSingleUser(single)).toBe(true);
    expect(hasOrgSurface(single)).toBe(false);
    expect(isSingleUser(user("agent_system"))).toBe(false);
    expect(hasOrgSurface(user("agent_system"))).toBe(false);
  });

  it("the two predicates together separate all three modes", () => {
    // agent_system is deliberately neither: one team, no org surface, not a
    // single person. What must hold is that no two modes share a signature.
    const signatures = MODES.map((mode) => `${isSingleUser(user(mode))}/${hasOrgSurface(user(mode))}`);
    expect(signatures).toEqual(["true/false", "false/false", "false/true"]);
    expect(new Set(signatures).size).toBe(MODES.length);
  });
});
