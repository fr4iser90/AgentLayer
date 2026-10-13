import { describe, expect, it } from "vitest";
import type { AuthUser } from "./AuthContext";
import {
  allowedNavItems,
  friendSystemEnabled,
  navItemAllowed,
  pathForNavItem,
} from "./tenantSurface";

function user(overrides: Partial<AuthUser> = {}): AuthUser {
  return { id: "u1", email: "a@b.c", role: "user", ...overrides };
}

describe("friendSystemEnabled", () => {
  it("treats an absent flag as enabled", () => {
    // A /auth/me payload from before schema_137 has no key. Reading that as
    // disabled would hide a live subsystem from everyone on upgrade.
    expect(friendSystemEnabled(user())).toBe(true);
    // No user yet (auth still loading) is not evidence the operator switched
    // anything off either — the API is the gate, this only decorates the nav.
    expect(friendSystemEnabled(undefined)).toBe(true);
  });

  it("honours the flag both ways", () => {
    expect(friendSystemEnabled(user({ friend_system_enabled: false }))).toBe(false);
    expect(friendSystemEnabled(user({ friend_system_enabled: true }))).toBe(true);
  });
});

describe("navItemAllowed for friends", () => {
  it("denies when the operator switched the subsystem off, even with full nav", () => {
    // The tenant allowlist is not the only gate: an unrestricted tenant still
    // loses friends when the instance-level switch is off.
    expect(navItemAllowed(user({ friend_system_enabled: false }), "friends")).toBe(false);
  });

  it("allows when enabled and the tenant has no explicit allowlist", () => {
    expect(navItemAllowed(user({ friend_system_enabled: true }), "friends")).toBe(true);
  });

  it("still respects the tenant allowlist when the subsystem is on", () => {
    const listed = user({
      friend_system_enabled: true,
      allowed_nav: ["home", "chat", "friends"],
    });
    expect(navItemAllowed(listed, "friends")).toBe(true);

    const notListed = user({ friend_system_enabled: true, allowed_nav: ["home", "chat"] });
    expect(navItemAllowed(notListed, "friends")).toBe(false);
  });

  it("denies regardless of the tenant listing the item when the flag is off", () => {
    const listedButDisabled = user({
      friend_system_enabled: false,
      allowed_nav: ["home", "friends"],
    });
    expect(navItemAllowed(listedButDisabled, "friends")).toBe(false);
  });
});

describe("allowedNavItems accepts friends", () => {
  it("keeps friends rather than dropping it as unknown", () => {
    // Before friends was a known nav id, a tenant that listed it had the value
    // silently discarded, so the item could not be controlled per tenant.
    const u = user({ allowed_nav: ["home", "friends", "bogus"] });
    expect(allowedNavItems(u)).toEqual(["home", "friends"]);
  });
});

describe("pathForNavItem", () => {
  it("maps friends to its settings path like shares", () => {
    expect(pathForNavItem("friends")).toBe("/settings/friends");
    expect(pathForNavItem("shares")).toBe("/settings/shares");
    expect(pathForNavItem("projects")).toBe("/projects");
  });
});
