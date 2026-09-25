import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  auditUnnaviated,
  collectNavTargets,
  collectRoutes,
  declarationBlock,
  findBrokenFolds,
  findMissingDoors,
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

/**
 * The door rule, added in the same step that deleted the avatar menu's links
 * into `/admin` and `/org`. Until then the guard could see one nav container and
 * say OK while two of the four surfaces were reachable only from a dropdown with
 * its own copy of the gate — reachability was true by accident, in a place the
 * rule did not look.
 *
 * The matcher here is new to this guard (read an array literal out of TypeScript
 * source), so the parser gets the same suspicion as the rest: an annotated
 * declaration, a bracket inside a string, an arrow function inside a leaf.
 */
describe("nav guard makes every surface have a door in the app rail", () => {
  const PREFIXES = ["/settings", "/admin", "/org"];

  it("reads past the type annotation's brackets", () => {
    // `NavSection[]` puts a `[` before the value's `[`. Reading from the name
    // would return "[]" and report every door missing — or, if the caller
    // treated an empty read as "nothing to check", every door present.
    const src = `const APP_SECTIONS: NavSection[] = [
      { leaves: [{ to: "/admin", labelKey: "nav.admin", icon: Shield }] }
    ];`;
    expect(declarationBlock(src, "APP_SECTIONS")).toContain('to: "/admin"');
    expect(findMissingDoors(declarationBlock(src, "APP_SECTIONS") ?? "", ["/admin"])).toEqual([]);
  });

  it("is not truncated by a bracket inside a string", () => {
    const src = `const SURFACE_DOORS: SurfaceDoor[] = [
      { to: "/org", labelKey: "nav.brackets[a]", icon: Icon, open: (u) => ok(u) },
      { to: "/admin", labelKey: "nav.admin", icon: Icon, open: (u) => ok(u) }
    ];`;
    const block = declarationBlock(src, "SURFACE_DOORS") ?? "";
    expect(findMissingDoors(block, PREFIXES)).toEqual(["/settings"]);
  });

  it("reports nothing read as nothing read, not as a pass", () => {
    expect(declarationBlock("const OTHER = [];", "APP_SECTIONS")).toBeNull();
  });

  it("accepts a door below the prefix, since the leaf is the way in", () => {
    const src = `const APP_SECTIONS = [{ leaves: [{ to: "/settings/profile", labelKey: "s" }] }];`;
    expect(findMissingDoors(src, ["/settings"])).toEqual([]);
  });

  it("does not let a longer prefix count as a door", () => {
    // `/adminx` is a different area. Matching by prefix alone would let a rename
    // keep the rule green while `/admin` itself lost its link.
    const src = `const APP_SECTIONS = [{ leaves: [{ to: "/adminx", labelKey: "x" }] }];`;
    expect(findMissingDoors(src, ["/admin"])).toEqual(["/admin"]);
  });

  it("reads the app rail's list, not the file's whole link set", () => {
    // The way in cannot be inside the room: `ADMIN_SECTIONS` carries
    // `{ to: "/admin" }` and is mounted only once you are already there, so it
    // must not satisfy the rule. `findMissingDoors` cannot tell the two lists
    // apart by itself — the caller picks the declaration, and this pins that the
    // pick is narrow enough to matter.
    const src = `const APP_SECTIONS: NavSection[] = [
      { leaves: [{ to: "/chat", labelKey: "nav.chat", icon: Chat }] }
    ];
    const ADMIN_SECTIONS: NavSection[] = [
      { leaves: [{ to: "/admin", labelKey: "admin:overview", icon: Gauge, end: true }] }
    ];`;
    expect(findMissingDoors(src, ["/admin"])).toEqual([]);
    expect(findMissingDoors(declarationBlock(src, "APP_SECTIONS") ?? "", ["/admin"])).toEqual([
      "/admin"
    ]);
  });

  it("ignores an external leaf, which is not a door into a surface", () => {
    const src = `const APP_SECTIONS = [{ leaves: [{ to: "/org", labelKey: "x", external: true }] }];`;
    expect(findMissingDoors(src, ["/org"])).toEqual(["/org"]);
  });

  it("holds on the model the app actually ships", () => {
    // The fixtures above prove the matcher; this proves the matcher is aimed at
    // the real file, so deleting a door fails `npm run test` and not only the
    // guard invocation.
    const src = readFileSync(join(process.cwd(), "src/layout/navModel.ts"), "utf8");
    const blocks = ["APP_SECTIONS", "SURFACE_DOORS"].map((n) => declarationBlock(src, n));
    for (const block of blocks) expect(block).not.toBeNull();
    expect(findMissingDoors(blocks.filter(Boolean).join("\n"), PREFIXES)).toEqual([]);
  });
});

/**
 * Rule 6 — a fold is the one way a leaf stops being visible on its own, so a
 * fold that hides the wrong pages is a rail offering a door and deleting the
 * rooms behind it.
 *
 * The reader had already failed once before the rule existed: the leaf matcher
 * ran to the first `}` after `to: "…"`, which inside `children: [ … ]` is the
 * first child's closing brace. Every folded page therefore looked like a leaf
 * beside the door, and a fold that hid one was invisible to the guard rather
 * than reported. The tests below pin both halves — the fold is followed, and the
 * named list it points at is not read a second time at the top level, which is
 * how a model written the way the guard asks would be punished with a duplicate.
 */
type Target = { to: string; external: boolean; parent?: string; depth?: number };

describe("nav guard follows a fold one level down", () => {
  it("reads the pages a door folds", () => {
    const src = `const ADMIN_SECTIONS = [{ leaves: [{
      to: "/admin/interfaces",
      children: [{ to: "/admin/interfaces/bridges" }, { to: "/admin/interfaces/voice" }]
    }] }];`;
    expect(collectNavTargets(src)).toEqual([
      { to: "/admin/interfaces", external: false },
      { to: "/admin/interfaces/bridges", external: false, parent: "/admin/interfaces", depth: 2 },
      { to: "/admin/interfaces/voice", external: false, parent: "/admin/interfaces", depth: 2 }
    ]);
  });

  it("follows a fold written by name and reads it once", () => {
    // The named list keeps the door one line long. Scanning it at the top level
    // too would report each page as a child *and* as a leaf beside the door.
    const src = `const INTERFACES_CHILDREN: NavLeaf[] = [
      { to: "/admin/interfaces/bridges", icon: GitBranch },
      { to: "/admin/interfaces/voice", icon: Mic }
    ];
    const ADMIN_SECTIONS: NavSection[] = [
      { leaves: [{ to: "/admin/interfaces", children: INTERFACES_CHILDREN }] }
    ];`;
    const pairs = (collectNavTargets(src) as Target[]).map((t) => [t.to, t.parent ?? null]);
    expect(pairs).toEqual([
      ["/admin/interfaces", null],
      ["/admin/interfaces/bridges", "/admin/interfaces"],
      ["/admin/interfaces/voice", "/admin/interfaces"]
    ]);
  });

  it("keeps a child's external flag off the door", () => {
    // `external` decides whether a route has to exist. A door that inherited it
    // from its own fold would stop being a link and stop needing a page.
    const src = `{ to: "/docs", children: [{ to: "https://example.com", external: true }] }`;
    const [door, child] = collectNavTargets(src) as Target[];
    expect(door).toEqual({ to: "/docs", external: false });
    expect(child).toMatchObject({ to: "https://example.com", external: true });
  });

  it("keeps the door's own external flag", () => {
    const src = `{ to: "https://example.com", external: true, children: [{ to: "/docs" }] }`;
    expect(collectNavTargets(src)[0]).toEqual({ to: "https://example.com", external: true });
  });

  it("reports a fold it cannot read instead of passing it", () => {
    // `children: SOMETHING` where SOMETHING is not a list in this file — moved to
    // another module, renamed, mistyped. Quiet here means the rule certifies a
    // group it never saw.
    const src = `{ to: "/admin/interfaces", children: INTERFACES_FROM_A_PACKAGE }`;
    const targets = collectNavTargets(src) as Target[];
    expect(targets).toEqual([
      { to: "/admin/interfaces", external: false, foldUnreadable: "INTERFACES_FROM_A_PACKAGE" }
    ]);
    expect(findBrokenFolds(targets).map((p: { kind: string }) => p.kind)).toEqual(["unread"]);
  });
});

describe("nav guard judges what a fold hides", () => {
  const page = (to: string, parent: string, depth = 2): Target => ({
    to,
    external: false,
    parent,
    depth
  });
  const kinds = (...targets: Target[]) =>
    findBrokenFolds(targets).map((p: { kind: string }) => p.kind);

  it("accepts pages that sit below their door", () => {
    expect(
      findBrokenFolds([
        { to: "/admin/interfaces", external: false },
        page("/admin/interfaces/bridges", "/admin/interfaces"),
        page("/admin/interfaces/voice", "/admin/interfaces")
      ])
    ).toEqual([]);
  });

  it("fails a fold inside a fold", () => {
    // The nested second container this rail deleted, grown back one level lower.
    expect(
      kinds(page("/admin/interfaces/bridges/rooms", "/admin/interfaces/bridges", 3))
    ).toEqual(["nested"]);
  });

  it("fails a door listed among its own pages", () => {
    // The `/admin/interfaces` overview row: two rows, one page, both lit at once,
    // because a NavLink without `end` matches its descendants.
    expect(kinds(page("/admin/interfaces", "/admin/interfaces"))).toEqual(["self"]);
  });

  it("fails a page that is not below its door", () => {
    // Folding the interfaces door would hide a tools page that has no other row,
    // with nothing on screen saying where it went.
    expect(kinds(page("/admin/tools", "/admin/interfaces"))).toEqual(["outside"]);
  });

  it("fails a folded page that also stands beside its door", () => {
    expect(
      kinds(
        { to: "/admin/interfaces", external: false },
        { to: "/admin/interfaces/voice", external: false },
        page("/admin/interfaces/voice", "/admin/interfaces")
      )
    ).toEqual(["twice"]);
  });

  it("holds on the model the app ships, and proves the fold is there", () => {
    // "No fold is broken" is also true of a rail with no folds at all, which is
    // how a rule like this goes blind: the eight pages move back into a section
    // of their own, or a second overview row appears, and the check still says
    // OK. So the shipped model is asserted open *and* folded.
    const src = readFileSync(join(process.cwd(), "src/layout/navModel.ts"), "utf8");
    const targets = collectNavTargets(src) as Target[];
    const door = "/admin/interfaces";
    expect(findBrokenFolds(targets)).toEqual([]);
    expect(targets.filter((t) => t.to === door)).toHaveLength(1);
    const folded = targets.filter((t) => t.parent === door);
    expect(folded.length).toBeGreaterThan(1);
    for (const t of folded) expect(t.to.startsWith(`${door}/`)).toBe(true);
  });
});