import { describe, expect, it } from "vitest";
import {
  auditUnnaviated,
  collectNavTargets,
  collectRoutes,
  findOrphans,
  reachesPath,
  scanLayoutNav,
  unnaviatedPaths
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

describe("nav guard makes an exception name its way in", () => {
  // `/org/setup` sat on the unnaviated list as a bare path beside a note that
  // said "say how". Nobody had to answer it, which is the same as not asking:
  // the entry would have stayed green through the redirect being renamed, the
  // page being deleted, or a rail leaf appearing. These are the four ways the
  // sentence could rot, one test each.
  const routes = [{ path: "/org/setup", redirect: false }];
  const VIA = "src/auth/RequireOrgAdmin.tsx";
  const entry = { path: "/org/setup", reachedVia: VIA };
  const read = (rel: string) =>
    rel === VIA
      ? `return <Navigate to="/org/setup" replace state={{ from: location.pathname }} />;`
      : null;
  const kinds = (entries: unknown[], rs = routes, ts: { to: string; external: boolean }[] = []) =>
    auditUnnaviated(entries, rs, ts, read).map((p) => p.kind);

  it("accepts an entry whose file navigates there", () => {
    expect(kinds([entry])).toEqual([]);
  });

  it("reads all three navigation shapes", () => {
    expect(reachesPath(`to="/org/setup"`, "/org/setup")).toBe(true);
    expect(reachesPath(`navigate("/org/setup")`, "/org/setup")).toBe(true);
    expect(reachesPath("navigate(`/org/setup`)", "/org/setup")).toBe(true);
  });

  it("does not accept a mention that is not a navigation", () => {
    // This is precisely what the old baseline entry was: the path, in prose.
    expect(reachesPath("// /org/setup is reached from the guard", "/org/setup")).toBe(false);
    expect(reachesPath(`const target = "/org/setup";`, "/org/setup")).toBe(false);
  });

  it("does not let a longer path satisfy a shorter one", () => {
    // A rename to /org/setup-wizard must fail the old entry, not inherit it.
    expect(reachesPath(`to="/org/setup-wizard"`, "/org/setup")).toBe(false);
  });

  it("treats a dot in the path as a dot", () => {
    expect(reachesPath(`to="/a/b"`, "/a.b")).toBe(false);
  });

  it("fails an entry that names no file", () => {
    expect(kinds([{ path: "/org/setup" }])).toEqual(["no_how"]);
  });

  it("fails an unanswered TODO left by --update", () => {
    expect(kinds([{ path: "/org/setup", reachedVia: "TODO — wie ist die Stelle erreichbar?" }])).toEqual(
      ["no_how"]
    );
  });

  it("fails the shape the guard shipped with", () => {
    expect(kinds(["/org/setup"])).toEqual(["bare"]);
  });

  it("fails an entry with no path at all", () => {
    expect(kinds([{}])).toEqual(["malformed"]);
  });

  it("fails a pointer whose file is gone", () => {
    expect(kinds([{ path: "/org/setup", reachedVia: "src/auth/RequireOrg.tsx" }])).toEqual([
      "no_file"
    ]);
  });

  it("fails a pointer that stopped navigating — the rot nothing else can see", () => {
    // Same file, same route, the redirect now goes somewhere else. The app
    // still works; only the reason beside the entry is false.
    const moved = auditUnnaviated([entry], routes, [], () => `return <Navigate to="/org/team" />;`);
    expect(moved.map((p) => p.kind)).toEqual(["no_nav"]);
  });

  it("fails an entry for a route that no longer exists", () => {
    expect(kinds([entry], [])).toEqual(["gone"]);
  });

  it("fails an entry whose route joined the rail", () => {
    expect(kinds([entry], routes, [{ to: "/org/setup", external: false }])).toEqual(["in_rail"]);
  });

  it("treats a redirect route as not needing an exception", () => {
    expect(kinds([entry], [{ path: "/org/setup", redirect: true }])).toEqual(["gone"]);
  });

  it("reads paths out of both entry shapes", () => {
    // The orphan rule still has to see the paths after the schema grew.
    expect(unnaviatedPaths(["/org/setup", entry])).toEqual(["/org/setup", "/org/setup"]);
  });
});