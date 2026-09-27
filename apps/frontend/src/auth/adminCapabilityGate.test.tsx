import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ADMIN_CAPABILITIES, holdsCapability } from "../pages/admin/accessGating";
import { adminNav, navLeaves } from "../layout/navModel";
import type { AccessActor } from "../pages/admin/accessGating";
import type { AuthUser } from "./AuthContext";
import { RequireCapability } from "./RequireCapability";

/**
 * The rail and the router have to make the same claim about one page.
 *
 * `navModel.ts` decides which rows appear; `App.tsx` decides who gets served.
 * Nothing but this test reads both, which is how `/admin/run-traces` ended up
 * asking the platform operator in the route while its three endpoints asked
 * `observability.read`: an account the API let in had no page, and a page can
 * fail that way in either direction — a row that bounces the reader, or a route
 * that renders a page whose data 403s.
 *
 * So the parsers below are the load-bearing part and are pinned from both sides
 * like the nav guard's: one that quietly stops matching would report agreement
 * forever, which is worse than the drift it replaced.
 */

const authState = vi.hoisted(() => ({
  loading: false,
  accessToken: null as string | null,
  user: null as unknown as AuthUser | null
}));

vi.mock("./AuthContext", () => ({
  useAuth: () => authState
}));

const keys = vi.hoisted(() => ({ t: (key: string) => key }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: keys.t, i18n: { language: "en" } })
}));

const APP_SOURCE = readFileSync(join(process.cwd(), "src/App.tsx"), "utf8");
const NAV_SOURCE = readFileSync(join(process.cwd(), "src/layout/navModel.ts"), "utf8");

/** Route paths whose element is wrapped in `RequireCapability`. */
function guardedRoutes(source: string): Array<{ path: string; cap: string }> {
  const found: Array<{ path: string; cap: string }> = [];
  for (const match of source.matchAll(/<RequireCapability\s+cap="([^"]+)"/g)) {
    const route = source.lastIndexOf("<Route", match.index ?? 0);
    const path = /path="([^"]+)"/.exec(source.slice(route, match.index))?.[1];
    if (!path) {
      throw new Error(
        `A RequireCapability at index ${match.index} has no <Route path before it, ` +
          "so the guarded page cannot be named — the check would drop it silently."
      );
    }
    found.push({ path: `/${path}`, cap: match[1]! });
  }
  return found;
}

/** Leaves that carry a `cap`, with the path they point at. */
function cappedLeaves(source: string): Array<{ to: string; cap: string }> {
  const found: Array<{ to: string; cap: string }> = [];
  for (const match of source.matchAll(/\{[^{}]*?\bcap:\s*"([^"]+)"[^{}]*?\}/gs)) {
    const to = /\bto:\s*"([^"]+)"/.exec(match[0])?.[1];
    if (!to) continue;
    found.push({ to, cap: match[1]! });
  }
  // A leaf with `children` has `{` inside this match's reach and would be
  // skipped: count the declarations so that shape fails instead of agreeing.
  const declared = (source.match(/\bcap:\s*"/g) ?? []).length;
  if (declared !== found.length) {
    throw new Error(
      `${declared} leaf capabilities are declared but ${found.length} were parsed — ` +
        "the reader cannot see one of them (a folded leaf is the shape to look for)."
    );
  }
  return found;
}

const asUser = (partial: Record<string, unknown>) => partial as AuthUser;
const OPERATOR = asUser({ site_role: "site_admin", capabilities: [] });
const TRACE_READER = asUser({ site_role: "platform_operator", capabilities: ["observability.read"] });
const JOB_DELEGATE = asUser({ site_role: "platform_operator", capabilities: ["schedule.manage"] });

const railPaths = (user: AuthUser | null) => navLeaves(adminNav(user)).map((leaf) => leaf.to);

describe("the rail and the route table agree", () => {
  it("opens exactly the admin page this branch was written for", () => {
    // A second page is allowed, and belongs in its own commit: update this
    // expectation and expect the review of why its endpoint is scope-clean.
    expect(guardedRoutes(APP_SOURCE)).toEqual([{ path: "/admin/run-traces", cap: "observability.read" }]);
  });

  it("names the same capability on the leaf as on the route", () => {
    const fromRoutes = Object.fromEntries(guardedRoutes(APP_SOURCE).map((r) => [r.path, r.cap]));
    const fromLeaves = Object.fromEntries(cappedLeaves(NAV_SOURCE).map((l) => [l.to, l.cap]));
    expect(fromLeaves).toEqual(fromRoutes);
  });

  it("only spells slugs the backend knows", () => {
    for (const { cap } of cappedLeaves(NAV_SOURCE)) {
      expect(ADMIN_CAPABILITIES).toContain(cap);
    }
    for (const { cap } of guardedRoutes(APP_SOURCE)) {
      expect(ADMIN_CAPABILITIES).toContain(cap);
    }
  });

  it("does not invent a capability where the route asks a guard", () => {
    // Both parsers have to be able to say "none": a matcher that caught every
    // guard would make the two lists agree by construction.
    const sample = `
      <Route path="users" element={<RequireUserAdmin><AdminUsers /></RequireUserAdmin>} />
      <Route path="tools" element={<AdminTools />} />
    `;
    expect(guardedRoutes(sample)).toEqual([]);
    expect(
      cappedLeaves(`{ to: "/admin/tools", labelKey: "admin:toolsRegistryTitle", icon: Wrench }`)
    ).toEqual([]);
  });
});

describe("what the admin rail offers each reader", () => {
  it("shows the operator the whole area, as before", () => {
    const paths = railPaths(OPERATOR);
    expect(paths).toContain("/admin/run-traces");
    expect(paths).toContain("/admin/tools");
    expect(paths).toContain("/admin/users");
    expect(paths).toContain("/admin/interfaces/voice");
  });

  it("shows a delegated holder the page they hold and nothing they would bounce on", () => {
    expect(railPaths(TRACE_READER)).toEqual(["/admin/run-traces", "/"]);
  });

  it("shows a holder of a slug with no page just the way out", () => {
    // Honest for now: `schedule.manage` opens endpoints, and no admin leaf may
    // claim a route until that page stops asking for `schedules_allowed`.
    expect(railPaths(JOB_DELEGATE)).toEqual(["/"]);
  });

  it("does not treat an unloaded identity as a denial", () => {
    expect(railPaths(null)).toContain("/admin/tools");
  });
});

describe("holdsCapability", () => {
  it("grants every slug to a site admin and only the grant to anyone else", () => {
    expect(holdsCapability(OPERATOR, "observability.read")).toBe(true);
    expect(holdsCapability(TRACE_READER, "observability.read")).toBe(true);
    expect(holdsCapability(TRACE_READER, "schedule.manage")).toBe(false);
    expect(holdsCapability(JOB_DELEGATE, "observability.read")).toBe(false);
  });

  it("trims and lowercases a grant the way the backend does", () => {
    expect(holdsCapability({ capabilities: ["  Observability.Read "] }, "observability.read")).toBe(true);
  });

  it("does not inherit the legacy role read the area itself still has", () => {
    // `require_admin_scope` never accepted `role === "admin"`, so a capability
    // guard must not either; `isSiteAdmin` keeps it for the operator surface.
    const legacy = { site_role: null, role: "admin", capabilities: [] } as unknown as AccessActor;
    expect(holdsCapability(legacy, "observability.read")).toBe(false);
  });
});

function renderGuarded(user: AuthUser | null, loading = false) {
  authState.user = user;
  authState.loading = loading;
  return render(
    <MemoryRouter initialEntries={["/admin/run-traces"]}>
      <Routes>
        <Route
          path="/admin/run-traces"
          element={
            <RequireCapability cap="observability.read">
              <div>TRACES</div>
            </RequireCapability>
          }
        />
        <Route path="/chat" element={<div>AT-CHAT</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("RequireCapability at /admin/run-traces", () => {
  beforeEach(() => {
    authState.loading = false;
    authState.accessToken = "tok";
  });

  it("serves the holder the API already serves", () => {
    renderGuarded(TRACE_READER);
    expect(screen.getByText("TRACES")).toBeInTheDocument();
  });

  it("still serves the platform operator", () => {
    renderGuarded(OPERATOR);
    expect(screen.getByText("TRACES")).toBeInTheDocument();
  });

  it("keeps the legacy admin payload in, because the area always had it", () => {
    renderGuarded(asUser({ site_role: null, role: "admin", capabilities: [] }));
    expect(screen.getByText("TRACES")).toBeInTheDocument();
  });

  it("sends anyone else to their own landing page", () => {
    renderGuarded(asUser({ site_role: "platform_operator", capabilities: ["user.manage"] }));
    expect(screen.queryByText("TRACES")).toBeNull();
    expect(screen.getByText("AT-CHAT")).toBeInTheDocument();
  });

  it("waits for the session instead of bouncing it", () => {
    renderGuarded(TRACE_READER, true);
    expect(screen.queryByText("TRACES")).toBeNull();
    expect(screen.getByText("auth:loading")).toBeInTheDocument();
  });
});