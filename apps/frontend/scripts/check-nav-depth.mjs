#!/usr/bin/env node
/**
 * Nav-depth and reachability guard.
 *
 * Measured before the rail: five components each carried a nav container — the
 * top bar in `AppLayout` (five items visible, six behind a `More` dropdown) plus
 * sidebars in `SettingsLayout`, `AdminLayout`, `OrgAdminLayout` and
 * `InterfacesLayout`. The last one mounted *inside* the admin sidebar, so
 * `/admin/interfaces/voice` sat three containers deep, and nothing could say so
 * because the answer was spread over four files.
 *
 * Three rules, all static, all cheap:
 *
 * 1. **One nav container.** Among `src/layout/*.tsx` only `AppShell.tsx` may
 *    carry an area nav (`<nav>` or `NavLink`). A layout that grows its own
 *    sidebar of area links is the regression this exists for; the rail gets a
 *    section instead. Content panels — `CollapsibleSidebarShell`'s conversation
 *    list — are not area nav and are not caught.
 * 2. **No dead leaves.** Every `to:` in `navModel.ts` must resolve to a route in
 *    `App.tsx`. A rail link to a removed page is invisible until clicked.
 * 3. **No orphan areas.** Every non-redirect child route of `/admin`,
 *    `/admin/interfaces`, `/org` and `/settings` must appear as a leaf. This is
 *    the "every area visible, reachable in one click" rule — an area that exists
 *    but is not in the rail is only reachable by typing the URL.
 * 4. **An exception must point at its way in.** Every route on the unnaviated
 *    list carries `reachedVia`: the file that navigates there instead of the
 *    rail. The note beside that list has always said "say how" and nothing ever
 *    read it back, so an entry stayed a permission long after the sentence
 *    behind it could have stopped being true. The guard now opens the named file
 *    and looks for the navigation: route gone, leaf added, or a pointer that no
 *    longer points anywhere, and the entry fails.
 *
 * Run with --update to re-record the unnaviated allowlist after adding a route
 * that is deliberately not in the rail. Recorded `reachedVia` values are carried
 * over — an update that rewrote the file from scratch would quietly delete the
 * reasons; a new entry gets a TODO that has to be answered before a run passes.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const LAYOUT = join(SRC, "layout");
const APP = join(SRC, "App.tsx");
const MODEL = join(LAYOUT, "navModel.ts");
const BASELINE = join(__dirname, "nav-depth-baseline.json");

/** The one file allowed to carry an area nav. */
const SHELL = "AppShell.tsx";

/** The rail's own definitions — exempt by name, see `scanLayoutNav`. */
const MODEL_FILE = "navModel.ts";

/** Surfaces whose direct children must all be in the rail. */
const GUARDED_PREFIXES = ["/admin", "/admin/interfaces", "/org", "/settings"];

/**
 * End of a JSX tag, honouring `{…}` expressions and string literals: a route's
 * `element` prop contains `>` inside arrows and `"` inside paths, so a naive
 * `indexOf(">")` truncates the tag and loses `path`.
 */
function tagEnd(src, from) {
  let depth = 0;
  let quote = null;
  for (let i = from; i < src.length; i += 1) {
    const ch = src[i];
    if (quote) {
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
    } else if (ch === "{") {
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
    } else if (ch === ">" && depth === 0) {
      return i;
    }
  }
  return src.length;
}

function joinPath(segments) {
  const parts = segments.filter((s) => s && s !== "/");
  return parts.length ? `/${parts.join("/")}` : "/";
}

/**
 * Absolute route paths from `App.tsx`, in document order.
 *
 * Route paths there are relative and nested, so `/admin/interfaces/bridges` only
 * exists as the sum of three `path=` attributes. A guard that read them flat
 * would see `path="bridges"` and call every admin leaf a dead link.
 */
export function collectRoutes(src) {
  const routes = [];
  const stack = [];
  const re = /<Route\b|<\/Route>/g;
  let m;
  while ((m = re.exec(src))) {
    if (m[0] === "</Route>") {
      stack.pop();
      continue;
    }
    const end = tagEnd(src, m.index);
    const tag = src.slice(m.index, end + 1);
    const pathMatch = /\bpath="([^"]*)"/.exec(tag);
    const seg = pathMatch ? pathMatch[1] : null;
    if (seg !== null) {
      routes.push({
        path: joinPath([...stack, seg]),
        redirect: /element=\{\s*<Navigate\b/.test(tag)
      });
    }
    // A pathless layout route (`<Route element={<X/>}>`) still nests its
    // children, so it goes on the stack even without a path.
    if (!/\/>$/.test(tag)) stack.push(seg);
  }
  return routes;
}

/** Every `to:` literal in the nav model, with the leaf's own text beside it. */
export function collectNavTargets(src) {
  const out = [];
  // Leaf objects hold no nested braces, so the first `}` closes them.
  const re = /\{\s*to:\s*"([^"]+)"([^}]*)\}/g;
  let m;
  while ((m = re.exec(src))) {
    out.push({ to: m[1], external: /\bexternal:\s*true\b/.test(m[2]) });
  }
  return out;
}

/**
 * Files under `src/layout/` that carry an area nav.
 *
 * `<nav>` or `NavLink` is the signal, not `<aside>`: `CollapsibleSidebarShell`
 * is also an `<aside>` and also lives here, but it holds a conversation list,
 * not a list of areas. A rule that caught it would be widened on the first
 * honest use and then catch nothing.
 */
export function scanLayoutNav(fileName, src) {
  // MODEL is an absolute path; the caller hands it a bare file name.
  if (fileName === SHELL || fileName === MODEL_FILE) return [];
  const offenders = [];
  if (/<nav\b/.test(src)) offenders.push("<nav>");
  if (/\bNavLink\b/.test(src)) offenders.push("NavLink");
  return offenders;
}

/**
 * Guarded child routes with no leaf.
 *
 * "Child" means one segment below the prefix, so `/admin/interfaces` counts for
 * `/admin` and `/admin/interfaces/voice` counts for `/admin/interfaces` — the
 * interfaces leaves join the admin rail only while inside the area, which is
 * exactly why both prefixes are guarded separately.
 */
export function findOrphans(routes, targets, unnaviated) {
  const navSet = new Set(targets.filter((t) => !t.external).map((t) => t.to));
  const orphans = [];
  for (const route of routes) {
    if (route.redirect) continue;
    if (route.path === "/") continue;
    const parent = route.path.slice(0, route.path.lastIndexOf("/"));
    if (!GUARDED_PREFIXES.includes(parent && parent !== "" ? parent : "/")) continue;
    if (navSet.has(route.path)) continue;
    if (unnaviated.includes(route.path)) continue;
    orphans.push(route.path);
  }
  return orphans;
}

/**
 * Does this source navigate to exactly `path`?
 *
 * `<Navigate to="/org/setup">`, `to="/org/setup"` and `navigate("/org/setup")`
 * all count. A mention in prose does not: the sentence this replaces lived in a
 * `note` field, where a reader could only nod at it. The closing quote is part
 * of the match, so `/org/setup` cannot be satisfied by `/org/setup-something` —
 * matching a prefix would let a rename keep an entry green.
 */
export function reachesPath(src, path) {
  const needle = path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:to=|navigate\\()\\s*\\{?\\s*["'\`]${needle}["'\`]`).test(src);
}

/** Baseline entries are `{ path, reachedVia }`; a bare string is the old shape. */
export function unnaviatedPaths(entries) {
  return entries.map((e) => (typeof e === "string" ? e : e?.path)).filter(Boolean);
}

/**
 * Is every recorded exception still an exception that has a way in?
 *
 * `read` resolves a `reachedVia` path to file text, or `null` when the file is
 * gone — injected so this stays a pure decision over data the caller fetched.
 *
 * Four ways an entry rots, checked in the order a reader would fix them: the
 * route it excuses is no longer there; the route joined the rail, so the
 * exception is not needed; no file is named; the file named no longer navigates
 * there. The last one is the only kind no human would notice — the code still
 * works, it just works somewhere else.
 */
export function auditUnnaviated(entries, routes, targets, read) {
  const live = new Set(routes.filter((r) => !r.redirect).map((r) => r.path));
  const navSet = new Set(targets.filter((t) => !t.external).map((t) => t.to));
  const problems = [];
  for (const entry of entries) {
    const path = typeof entry === "string" ? entry : entry?.path;
    if (!path) {
      problems.push({ path: String(path ?? "?"), kind: "malformed" });
      continue;
    }
    if (typeof entry !== "object") {
      problems.push({ path, kind: "bare" });
      continue;
    }
    if (!live.has(path)) {
      problems.push({ path, kind: "gone" });
      continue;
    }
    if (navSet.has(path)) {
      problems.push({ path, kind: "in_rail" });
      continue;
    }
    const via = entry.reachedVia;
    if (!via || via.startsWith("TODO")) {
      problems.push({ path, kind: "no_how", via: via ?? null });
      continue;
    }
    const src = read(via);
    if (src === null) {
      problems.push({ path, kind: "no_file", via });
      continue;
    }
    if (!reachesPath(src, path)) problems.push({ path, kind: "no_nav", via });
  }
  return problems;
}

const UNNAVIATED_WHY = {
  malformed: "Eintrag ohne path — die Liste ist ein Objekt aus Pfad und Grund",
  bare: "Eintrag nur als Pfad — seit der Regel fehlt der Grund, wo die Stelle ohne Rail erreichbar ist",
  gone: "Route existiert nicht mehr — die Ausnahme entschuldigt nichts",
  in_rail: "Route hat inzwischen ein Rail-Blatt — die Ausnahme ist überflüssig",
  no_how: "Kein reachedVia — eine Ausnahme ohne Weg ist eine Erlaubnis ohne Argument",
  no_file: "reachedVia zeigt auf eine Datei, die nicht existiert",
  no_nav: "die genannte Datei navigiert nicht (mehr) auf diesen Pfad"
};

async function* walkLayout() {
  for (const entry of await readdir(LAYOUT, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith(".tsx")) {
      yield join(LAYOUT, entry.name);
    }
  }
}

export async function checkNavDepth() {
  const [appSrc, modelSrc, baseline] = await Promise.all([
    readFile(APP, "utf8"),
    readFile(MODEL, "utf8"),
    readFile(BASELINE, "utf8").then(JSON.parse)
  ]);
  const routes = collectRoutes(appSrc);
  const targets = collectNavTargets(modelSrc);
  const entries = baseline.unnaviated ?? [];

  const nested = [];
  for await (const file of walkLayout()) {
    const src = await readFile(file, "utf8");
    const name = relative(LAYOUT, file);
    for (const tag of scanLayoutNav(name, src)) {
      nested.push({ file: relative(ROOT, file), tag });
    }
  }

  const routeSet = new Set(routes.map((r) => r.path));
  const dead = targets.filter((t) => !t.external && !routeSet.has(t.to)).map((t) => t.to);
  const orphans = findOrphans(routes, targets, unnaviatedPaths(entries));

  const exceptions = await auditEntries(entries, routes, targets);

  return {
    nested,
    dead,
    orphans,
    exceptions,
    routes: routes.length,
    leaves: targets.length,
    recorded: entries.length
  };
}

/**
 * `auditUnnaviated` over the files on disk: a `reachedVia` that names nothing
 * readable is `null` rather than a throw, so a deleted file reports as itself
 * instead of hiding the other findings behind a stack trace.
 */
async function auditEntries(entries, routes, targets) {
  const via = [...new Set(entries.map((e) => e && e.reachedVia).filter(Boolean))];
  const texts = await Promise.all(
    via.map((rel) => readFile(join(ROOT, rel), "utf8").catch(() => null))
  );
  const sourceOf = new Map(via.map((rel, i) => [rel, texts[i]]));
  return auditUnnaviated(entries, routes, targets, (rel) => sourceOf.get(rel) ?? null);
}

async function update() {
  const appSrc = await readFile(APP, "utf8");
  const modelSrc = await readFile(MODEL, "utf8");
  const routes = collectRoutes(appSrc);
  const targets = collectNavTargets(modelSrc);
  const navSet = new Set(targets.filter((t) => !t.external).map((t) => t.to));
  const previous = await readFile(BASELINE, "utf8")
    .then((t) => JSON.parse(t).unnaviated ?? [])
    .catch(() => []);
  const keep = [];
  for (const route of routes) {
    if (route.redirect || route.path === "/" || navSet.has(route.path)) continue;
    const parent = route.path.slice(0, route.path.lastIndexOf("/"));
    if (!GUARDED_PREFIXES.includes(parent || "/")) continue;
    const old = previous.find((e) => (typeof e === "string" ? e : e?.path) === route.path);
    // Carried over verbatim, unanswered TODO and all: rewriting this file from
    // the route tree alone is how a re-record would silently drop every reason
    // on it. A new route gets the question, not an empty string — the audit
    // fails on the TODO, so the answer cannot be skipped by forgetting it.
    keep.push(
      old && typeof old === "object"
        ? old
        : { path: route.path, reachedVia: "TODO — wie ist die Stelle ohne Rail erreichbar?" }
    );
  }
  keep.sort((a, b) => a.path.localeCompare(b.path));
  await writeFile(
    BASELINE,
    JSON.stringify(
      {
        note: "Routes under a guarded prefix that are deliberately not in the rail. reachedVia names the file that navigates there instead — the guard opens it and looks, so the answer cannot go stale quietly.",
        unnaviated: keep
      },
      null,
      2
    ) + "\n"
  );
  console.log(
    `[nav-depth] recorded ${keep.length} unnaviated route(s): ${keep.map((k) => k.path).join(", ")}`
  );
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  if (process.argv.includes("--update")) {
    update().catch((e) => {
      console.error(e);
      process.exit(1);
    });
  } else {
    checkNavDepth()
      .then(({ nested, dead, orphans, exceptions, routes, leaves, recorded }) => {
        let failed = false;
        if (nested.length) {
          failed = true;
          console.error(
            `[nav-depth] FAILED - ${nested.length} layout(s) carry their own area nav:`
          );
          for (const n of nested) console.error(`  ${n.file}  ${n.tag}`);
          console.error(`Only ${SHELL} may. Add a section to navModel.ts instead.`);
        }
        if (dead.length) {
          failed = true;
          console.error(`[nav-depth] FAILED - ${dead.length} rail link(s) have no route:`);
          for (const d of dead) console.error(`  ${d}`);
        }
        if (orphans.length) {
          failed = true;
          console.error(`[nav-depth] FAILED - ${orphans.length} area(s) nobody can navigate to:`);
          for (const o of orphans) console.error(`  ${o}`);
          console.error("Add a leaf to navModel.ts, or --update with a reason.");
        }
        // A recorded exception is the one finding that cannot be seen from the
        // route tree: the app still works, the reason beside it just stopped
        // being true.
        if (exceptions.length) {
          failed = true;
          console.error(
            `[nav-depth] FAILED - ${exceptions.length} aufgezeichnete Rail-Ausnahme(n) ohne gültigen Weg:`
          );
          for (const e of exceptions)
            console.error(
              `  ${e.path}${e.via ? `  ${e.via}` : ""} — ${UNNAVIATED_WHY[e.kind]}`
            );
          console.error(
            "[nav-depth] reachedVia auf die Datei setzen, die dorthin navigiert, oder den Eintrag löschen, wenn die Stelle jetzt im Rail liegt."
          );
        }
        if (failed) process.exit(1);
        console.log(
          `[nav-depth] OK - ${routes} routes, ${leaves} rail leaves, one nav container, ${recorded} Ausnahme(n) mit Weg`
        );
      })
      .catch((e) => {
        console.error(e);
        process.exit(1);
      });
  }
}