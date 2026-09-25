import { describe, expect, it } from "vitest";
import {
  collectNavTargets,
  collectRoutes,
  findOrphans,
  scanLayoutNav
} from "../../scripts/check-nav-depth.mjs";

/**
 * The nav guard reads two files it does not own — `App.tsx` and `navModel.ts` —
 * and every matcher in this repo's guard family has failed silently at least
 * once. So the tests here are mostly about the parser being unable to lie:
 *
 * - `App.tsx` route paths are relative and nested. A flat reader would see
 *   `path="bridges"` and call every admin leaf a dead link, then get widened
 *   until it caught nothing.
 * - The nav-container rule had to be narrowed from `<aside>` to `<nav>`/`NavLink`
 *   after it flagged `CollapsibleSidebarShell`, which is a conversation panel.
 *   Both directions are pinned below, because a rule narrowed on one anecdote
 *   needs proof it still catches the thing it was written for.
 */

const APP = `
<Routes>
  <Route element={<AppLayout />}>
    <Route path="login" element={<LoginPage />} />
    <Route element={<RequireSession />}>
      <Route path="/" element={<HomePage />} />
      <Route path="chat" element={<ChatPage />} />
      <Route path="settings" element={<SettingsLayout />}>
        <Route index element={<Navigate to="/settings/profile" replace />} />
        <Route path="profile" element={<ProfileSettings />} />
      </Route>
      <Route path="admin" element={<RequireSiteAdmin />}>
        <Route index element={<AdminDashboard />} />
        <Route path="interfaces" element={<InterfacesLayout />}>
          <Route path="bridges" element={<AdminInterfacesBridgesPage />} />
          <Route path="llm" element={<Navigate to="../routing" replace />} />
        </Route>
        <Route path="tools" element={<AdminTools />} />
      </Route>
    </Route>
    <Route path="*" element={<DefaultLandingRedirect />} />
  </Route>
</Routes>
`;

describe("nav guard reads nested routes", () => {
  it("joins a route path with its ancestors", () => {
    const paths = collectRoutes(APP).map((r) => r.path);
    expect(paths).toContain("/admin/interfaces/bridges");
    expect(paths).toContain("/settings/profile");
    expect(paths).toContain("/chat");
  });

  it("keeps nesting through a pathless layout route", () => {
    // RequireSession has no path of its own. Dropping it from the stack instead
    // of nesting through it would report /admin as a sibling of nothing and
    // make every admin leaf look dead.
    const paths = collectRoutes(APP).map((r) => r.path);
    expect(paths).toContain("/admin");
    expect(paths).not.toContain("/interfaces");
  });

  it("marks a redirect route so it is not demanded in the rail", () => {
    const routes = collectRoutes(APP);
    expect(routes.find((r) => r.path === "/admin/interfaces/llm")?.redirect).toBe(true);
    expect(routes.find((r) => r.path === "/admin/tools")?.redirect).toBe(false);
  });

  it("does not treat a self-closing route as a parent", () => {
    // `path="login"` closes itself. If it stayed on the stack, `*` would come
    // out as /login/* and the reachability check would chase a route that does
    // not exist.
    const paths = collectRoutes(APP).map((r) => r.path);
    expect(paths).toContain("/login");
    expect(paths.some((p) => p.startsWith("/login/"))).toBe(false);
  });

  it("reads a path containing a quote-bearing element expression", () => {
    const src = `<Route path="x" element={<RequireRole role="a>b" />} />`;
    expect(collectRoutes(src).map((r) => r.path)).toEqual(["/x"]);
  });
});

describe("nav guard reads the rail", () => {
  it("reads leaves including multi-line ones", () => {
    const src = `
      { to: "/admin", labelKey: "admin:overview", icon: Gauge, end: true },
      {
        to: "/admin/interfaces/model-policies",
        labelKey: "admin:interfacesModelPoliciesTitle",
        icon: KeyRound
      },
    `;
    expect(collectNavTargets(src).map((t) => t.to)).toEqual([
      "/admin",
      "/admin/interfaces/model-policies"
    ]);
  });

  it("does not demand a route for an external leaf", () => {
    const src = `{ to: "https://github.com/x", external: true, labelKey: "nav.github" }`;
    expect(collectNavTargets(src)).toEqual([{ to: "https://github.com/x", external: true }]);
  });
});

describe("nav guard finds a second nav container", () => {
  it("flags a layout that grows its own nav", () => {
    // The exact regression: AdminLayout's old sidebar.
    expect(scanLayoutNav("AdminLayout.tsx", '<aside><nav aria-label="x">…</nav></aside>')).toEqual(
      ["<nav>"]
    );
    expect(scanLayoutNav("AdminLayout.tsx", '<NavLink to="/admin">x</NavLink>')).toEqual([
      "NavLink"
    ]);
  });

  it("exempts the shell and the model", () => {
    expect(scanLayoutNav("AppShell.tsx", "<nav>x</nav>")).toEqual([]);
    expect(scanLayoutNav("navModel.ts", "<nav>x</nav>")).toEqual([]);
  });

  it("does not flag a content panel that happens to be an aside", () => {
    // CollapsibleSidebarShell holds a conversation list, not a list of areas.
    // Flagging it got the rule widened into uselessness once already.
    expect(scanLayoutNav("CollapsibleSidebarShell.tsx", "<aside>{sidebar}</aside>")).toEqual([]);
  });
});

describe("nav guard finds areas nobody can reach", () => {
  const routes = [
    { path: "/admin", redirect: false },
    { path: "/admin/tools", redirect: false },
    { path: "/admin/discord", redirect: true },
    { path: "/admin/interfaces/bridges", redirect: false },
    { path: "/org/setup", redirect: false },
    { path: "/chat", redirect: false }
  ];
  const leaf = (to: string) => ({ to, external: false });

  it("flags a guarded child with no leaf", () => {
    expect(findOrphans(routes, [leaf("/admin")], [])).toEqual([
      "/admin/tools",
      "/admin/interfaces/bridges",
      "/org/setup"
    ]);
  });

  it("stands down once the leaf exists", () => {
    const covered = [
      "/admin",
      "/admin/tools",
      "/admin/interfaces/bridges",
      "/org/setup"
    ].map(leaf);
    expect(findOrphans(routes, covered, [])).toEqual([]);
  });

  it("skips redirects and routes outside a guarded surface", () => {
    // /admin/discord redirects, /chat is not under a guarded prefix — neither
    // may be demanded in the rail. /org/setup is allowlisted here so this test
    // says only what its name claims.
    expect(
      findOrphans(routes, [], ["/admin/tools", "/admin/interfaces/bridges", "/org/setup"])
    ).toEqual([]);
  });

  it("honours the recorded allowlist", () => {
    expect(findOrphans(routes, [leaf("/admin"), leaf("/admin/tools")], ["/org/setup"])).toEqual([
      "/admin/interfaces/bridges"
    ]);
  });
});