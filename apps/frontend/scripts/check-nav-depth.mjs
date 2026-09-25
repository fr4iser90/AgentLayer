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
 * Seven rules, all static, all cheap:
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
 * 5. **Every surface has a door in the app rail.** `/settings`, `/admin` and
 *    `/org` must each have an app-rail leaf that starts at them — one inside
 *    `APP_SECTIONS`, the two management doors inside `SURFACE_DOORS`. Until
 *    wave 2 the platform-admin and organization links lived in the avatar menu,
 *    so `check-nav-depth` saw one nav container and zero doors for two of the
 *    four surfaces — deleting those links without this rule would have hidden
 *    both areas behind a typed URL. The rule is structural: it asks whether a
 *    door exists in the list, not whether the current role sees it, because
 *    gating happens at runtime and the guard cannot have a user.
 * 6. **A fold hides the pages below its own door.** A leaf may carry `children`,
 *    folded in place inside the same list, and four things hold: the fold is one
 *    level deep, the door is not one of its own pages, every page sits below the
 *    door's path, and no folded page also stands beside it. `/admin/interfaces`
 *    was in the admin rail twice — `Interfaces` in the platform section,
 *    `Overview` in a section of its own — and both lit at once, because the
 *    area's list was spliced in beside the door that opened it. A fold failing
 *    here hides an unrelated area behind an unrelated door, which is worse than
 *    the duplicate it replaces.
 * 7. **A label the rail asks for must be asked for.** Every leaf key of `nav`
 *    and `footer` in `src/locales/en/common.json` has to appear as a whole key
 *    in a source file. `nav.more` and `nav.connections` outlived the `More`
 *    dropdown by a wave of the redesign and `footer.github` outlived the link in
 *    the footer; nothing on screen and no check said so. A catalogue entry is
 *    invisible in exactly the way a rail leaf pointing at a deleted route is,
 *    which this guard already refuses — rule 2, one layer earlier in the chain.
 *
 * Run with --update to re-record the unnaviated allowlist after adding a route
 * that is deliberately not in the rail. Recorded `reachedVia` values are carried
 * over — an update that rewrote the file from scratch would quietly delete the
 * reasons; a new entry gets a TODO that has to be answered before a run passes.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { stripComments } from "./strip-comments.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const LAYOUT = join(SRC, "layout");
const APP = join(SRC, "App.tsx");
const MODEL = join(LAYOUT, "navModel.ts");
const BASELINE = join(__dirname, "nav-depth-baseline.json");

/** The catalogue rule 7 reads, and the namespace its keys are qualified with. */
const LOCALES = join(SRC, "locales");
const CATALOGUE = join(LOCALES, "en", "common.json");
const CATALOGUE_NS = "common";

/** The one file allowed to carry an area nav. */
const SHELL = "AppShell.tsx";

/** The rail's own definitions — exempt by name, see `scanLayoutNav`. */
const MODEL_FILE = "navModel.ts";

/** Surfaces whose direct children must all be in the rail. */
const GUARDED_PREFIXES = ["/admin", "/admin/interfaces", "/org", "/settings"];

/** Surfaces that must each have a door in the app rail — see rule 5. */
const SURFACE_PREFIXES = ["/settings", "/admin", "/org"];

/**
 * The declarations that make up the app rail's static content.
 *
 * Two, because the doors into the other surfaces are a list of their own
 * (`SURFACE_DOORS`) that `appNav` appends after gating. Reading the compiled
 * return value of `appNav` instead would need a user, and a guard has none.
 */
const APP_RAIL_BLOCKS = ["APP_SECTIONS", "SURFACE_DOORS"];

/**
 * Catalogue namespaces whose every leaf key must have a consumer — rule 7.
 *
 * Two, deliberately. A substring scan over all of `common.json` called 341 of
 * 3099 keys unreferenced, and the top hits were the scan being wrong rather
 * than the keys being dead: `notifications.daysAgo_one` is looked up by i18next
 * from the base name, `chat:err.${code}` is assembled at runtime. A rule over
 * the whole catalogue would need an exception list nobody can audit, which is a
 * different job from deleting the three keys this step deletes.
 *
 * `nav` and `footer` are the two the rail and the app frame read by literal
 * key, so inside them a key with no consumer means one thing only: whatever
 * asked for it is gone.
 */
const LABELED_NAMESPACES = ["nav", "footer"];

/**
 * The source text of one array declaration's value, brackets matched.
 *
 * The search for `[` starts at the `=`, not at the name: these declarations are
 * annotated (`const APP_SECTIONS: NavSection[] = [`), and the first bracket
 * after the name belongs to the type — reading from there returns `"[]"` and
 * every rule built on it silently passes with nothing in the list.
 *
 * String literals are consumed whole, so a `]` inside a label cannot close the
 * block early, and the array it is written in is where a door either is or is
 * not.
 */
export function declarationBlock(src, name) {
  const span = declarationSpan(src, name);
  return span ? src.slice(span[0], span[1] + 1) : null;
}

/** `declarationBlock` with the offsets, for reading a file in two passes. */
function declarationSpan(src, name) {
  const at = src.indexOf(`const ${name}`);
  if (at < 0) return null;
  const assign = src.indexOf("=", at);
  if (assign < 0) return null;
  const open = src.indexOf("[", assign);
  if (open < 0) return null;
  const close = spanEnd(src, open);
  return close < 0 ? null : [open, close + 1];
}

/**
 * Index of the character that closes the bracket opened at `open`, or -1.
 *
 * Brackets, parens and braces all count towards the depth because a leaf's value
 * may be an arrow function (`open: (u) => …`), and string literals are consumed
 * whole, so a bracket written inside a label cannot close the block early.
 */
function spanEnd(src, open) {
  let depth = 0;
  let quote = null;
  for (let i = open; i < src.length; i += 1) {
    const ch = src[i];
    if (quote) {
      if (ch === "\\") i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") quote = ch;
    else if (ch === "[" || ch === "(" || ch === "{") depth += 1;
    else if (ch === "]" || ch === ")" || ch === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * Which surfaces the app rail has no door into.
 *
 * A door is a leaf whose path is the prefix or something below it — the admin
 * door is `/admin` itself, the settings door is `/settings/profile`, and both
 * count. The caller hands in the app rail's own declarations: feeding this the
 * whole model would let `ADMIN_SECTIONS`' `/admin` overview satisfy the rule
 * from inside the area it is supposed to be the way into.
 */
export function findMissingDoors(appRailSrc, prefixes = SURFACE_PREFIXES) {
  const reached = collectNavTargets(appRailSrc)
    .filter((t) => !t.external)
    .map((t) => t.to.replace(/\/+$/, ""));
  return prefixes.filter((p) => !reached.some((to) => to === p || to.startsWith(`${p}/`)));
}

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

/**
 * Every `to:` in the nav model — doors, and the pages folded under them.
 *
 * A folded door broke the first version of this reader. It matched `{ to: "…"`
 * up to the *first* `}`, which for a door is the close of its first child rather
 * than the close of the door, so the door read as no door at all and every page
 * inside it vanished from the list — which rule 3 would have reported as areas
 * nobody can reach, eventually leading to the guard being widened until it
 * caught nothing. Objects are matched by bracket now, and a fold is followed one
 * level down, with the door's path beside each child so rule 6 can judge it.
 *
 * A fold may be written inline or by name (`children: INTERFACES_CHILDREN`), so
 * the named list is read out of the same file and blanked from the top-level
 * pass: leaving it visible would report the same page twice, once as a door's
 * child and once as a leaf beside it, and the model would be punished for the
 * shape the guard itself asks for.
 */
export function collectNavTargets(src) {
  const lists = foldLists(src);
  const out = [];
  collectLevel(maskDeclarations(src, lists), null, 1, out, lists);
  return out;
}

/** The named lists a `children:` refers to, resolved to their source or `null`. */
function foldLists(src) {
  const lists = new Map();
  for (const m of src.matchAll(/\bchildren:\s*([A-Za-z_$][\w$]*)/g)) {
    lists.set(m[1], declarationBlock(src, m[1]));
  }
  return lists;
}

/**
 * The file with those lists replaced by spaces of the same length.
 *
 * Same length, so every other offset in the text still means what it meant — the
 * masking is done once, over the original source, and nothing re-reads it
 * positionally afterwards.
 */
function maskDeclarations(src, lists) {
  let masked = src;
  for (const name of lists.keys()) {
    const span = declarationSpan(src, name);
    if (!span) continue;
    masked = masked.slice(0, span[0]) + " ".repeat(span[1] - span[0]) + masked.slice(span[1]);
  }
  return masked;
}

function collectLevel(src, parent, depth, out, lists) {
  const re = /\{\s*to:\s*"([^"]+)"/g;
  let m;
  while ((m = re.exec(src))) {
    const end = spanEnd(src, m.index);
    if (end < 0) continue;
    const body = src.slice(m.index, end + 1);
    const ref = /\bchildren:\s*(\[|[A-Za-z_$][\w$]*)/.exec(body);
    let own = body;
    if (ref) {
      // The door's own flags are read without its fold: `external: true` belongs
      // to a child, and a door that inherits it stops being a link at all.
      const close = ref[1] === "[" ? spanEnd(body, body.indexOf("[", ref.index)) : -1;
      own = close > 0 ? body.slice(0, ref.index) + body.slice(close + 1) : body.slice(0, ref.index);
    }
    const leaf = { to: m[1], external: /\bexternal:\s*true\b/.test(own) };
    if (parent) {
      leaf.parent = parent;
      // 2 = a page folded under one door; 3 and more = a fold inside a fold.
      leaf.depth = depth;
    }
    if (ref) {
      const block = ref[1] === "[" ? body.slice(ref.index) : lists.get(ref[1]);
      if (!block) leaf.foldUnreadable = ref[1];
      out.push(leaf);
      if (block) collectLevel(block, leaf.to, depth + 1, out, lists);
    } else {
      out.push(leaf);
    }
    re.lastIndex = end;
  }
}

/**
 * Folds that are not folds of the pages they hide. See rule 6.
 *
 * Five ways to get it wrong, one kind each: a fold the rule cannot read, a fold
 * inside a fold (the nested sidebar, back again), a door listed among its own
 * pages (the area twice in one list), a page that is not below its door
 * (collapsing it hides another area), and a folded page that also stands beside
 * its door.
 */
export function findBrokenFolds(targets) {
  const top = new Set(targets.filter((t) => !t.parent && !t.external).map((t) => t.to));
  const problems = [];
  for (const leaf of targets) {
    if (leaf.foldUnreadable) {
      problems.push({ to: leaf.to, kind: "unread", detail: leaf.foldUnreadable });
      continue;
    }
    if (!leaf.parent) continue;
    if (leaf.depth > 2) {
      problems.push({ to: leaf.to, parent: leaf.parent, kind: "nested" });
    } else if (leaf.to === leaf.parent) {
      problems.push({ to: leaf.to, parent: leaf.parent, kind: "self" });
    } else if (!leaf.to.startsWith(`${leaf.parent}/`)) {
      problems.push({ to: leaf.to, parent: leaf.parent, kind: "outside" });
    } else if (top.has(leaf.to)) {
      problems.push({ to: leaf.to, parent: leaf.parent, kind: "twice" });
    }
  }
  return problems;
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

const FOLD_WHY = {
  nested: "Gruppe in einer Gruppe — die Falz ist eine Ebene tief, darunter käme die ausgelagerte Sidebar zurück, die dieser Rail abgeschafft hat",
  self: "die Tür steht als eine ihrer eigenen Seiten — die Fläche erscheint zweimal in einer Liste, beide Zeilen leuchten",
  outside: "die Seite liegt nicht unter dem Pfad ihrer Tür — zugeklappt verschwindet sie hinter einer fachfremden Tür",
  twice: "die Seite liegt auch als Blatt neben ihrer Tür — zwei Zeilen, eine Seite",
  unread: "children: zeigt auf einen Namen, der in navModel.ts kein Array ist — die Regel kann die Gruppe nicht lesen"
};

async function* walkLayout() {
  for (const entry of await readdir(LAYOUT, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith(".tsx")) {
      yield join(LAYOUT, entry.name);
    }
  }
}

/**
 * Every leaf key under `namespace` in the catalogue, dotted and unqualified.
 *
 * `nav.loading` in `common.json` is asked for as `nav.loading`, not
 * `common:nav.loading` — the default namespace is implicit in `t()` — so the
 * key and the reference are the same shape once the namespace is the prefix.
 */
export function leafLabelKeys(catalogue, namespace) {
  const out = [];
  const walk = (node, prefix) => {
    for (const [name, value] of Object.entries(node ?? {})) {
      const key = prefix ? `${prefix}.${name}` : name;
      if (value && typeof value === "object") walk(value, key);
      else out.push(key);
    }
  };
  walk(catalogue?.[namespace], namespace);
  return out;
}

/**
 * Keys nothing quotes, and the namespaces this rule cannot read.
 *
 * A reference is the key inside quotes, with or without the catalogue's own
 * namespace in front: `t("nav.home")`, `labelKey: "nav.admin"`, and
 * `t("common:nav.dashboard")` where a component names the namespace explicitly.
 * Plain substring matching is the trap here, and was wrong twice while writing
 * this — once by counting `"connections"` (a route path) as a consumer of
 * `nav.connections`, once by matching only `"nav.x"` and calling the ten
 * `common:`-qualified lookups dead. So the quote is required on both sides and
 * the key must start at it, which is what makes `"connections"` not count.
 *
 * Comments are stripped first, for the reason `check-ink-color.mjs` gives: this
 * file's own header now names `nav.more` and `nav.connections`, and a rule that
 * read its own documentation as a consumer would certify the keys it exists to
 * delete.
 *
 * `dynamic` is the finding that keeps the rule honest. A key assembled at
 * runtime — `` t(`nav.${suffix}`) `` — is invisible to any scan, and an
 * invisible key is a pass nobody earned. So a namespace where it happens stops
 * being judged and says so, the same way an unreadable declaration block does
 * for rule 5.
 */
export function findDeadLabels({ catalogue, sources, namespaces = LABELED_NAMESPACES }) {
  const unreadable = [];
  const dead = [];
  const stripped = new Map([...sources].map(([file, text]) => [file, stripComments(text)]));

  // Every string literal in the sources, as the exact text between its quotes.
  const refs = new Set();
  for (const text of stripped.values()) {
    for (const re of [/"([^"\n]*)"/g, /'([^'\n]*)'/g, /`([^`]*)`/g]) {
      for (const m of text.matchAll(re)) refs.add(m[1]);
    }
  }
  const asked = (key) => refs.has(key) || refs.has(`${CATALOGUE_NS}:${key}`);

  for (const ns of namespaces) {
    if (!catalogue?.[ns]) {
      unreadable.push({ ns, kind: "absent", detail: `${CATALOGUE_NS}.json hat kein ${ns}` });
      continue;
    }
    const dynamic = dynamicLabel(ns);
    const where = [...stripped].flatMap(([file, text]) =>
      [...text.matchAll(dynamic)].map(() => file)
    );
    if (where.length) {
      unreadable.push({
        ns,
        kind: "dynamic",
        detail: `${[...new Set(where)].join(", ")} setzt ${ns}-Keys zur Laufzeit zusammen`
      });
      continue;
    }
    for (const key of leafLabelKeys(catalogue, ns)) {
      if (!asked(key)) dead.push(key);
    }
  }
  return { dead, unreadable };
}

/**
 * A label key put together at runtime, in either shape that does it: a template
 * (`` t(`nav.${suffix}`) ``) or a concatenation (`t("nav." + suffix)`).
 *
 * Compiled per namespace rather than memoised over `LABELED_NAMESPACES`, so a
 * caller that judges a namespace outside that list is judged and not crashed on.
 */
function dynamicLabel(namespace) {
  const ns = namespace.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\`[^\`]*?${ns}\\.\\$\\{|"${ns}\\."\\s*\\+`, "g");
}

/**
 * Source files rule 7 reads as consumers, by path relative to `src/`.
 *
 * Test files are not among them. A key quoted only inside `*.test.ts` is a key
 * a test asserts about and no user is ever shown — which is the state the three
 * keys this rule was written for were in, dead and wearing a green test. The
 * catalogues are out for the same reason in reverse: they define the keys, so
 * reading one as its own consumer would make every key self-certifying.
 */
export function isLabelSource(relativeToSrc) {
  const path = relativeToSrc.split("\\").join("/");
  if (!/\.tsx?$/.test(path)) return false;
  if (path === "locales" || path.startsWith("locales/")) return false;
  if (/\.(test|stories)\.tsx?$/.test(path)) return false;
  return true;
}

const LABEL_SOURCE_SKIP = ["locales"];

async function* walkLabelSources(dir = SRC) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const file = join(dir, entry.name);
    const rel = relative(SRC, file).split("\\").join("/");
    if (entry.isDirectory()) {
      if (!LABEL_SOURCE_SKIP.includes(rel)) yield* walkLabelSources(file);
    } else if (isLabelSource(rel)) {
      yield file;
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

  // Rule 5 is read out of the model's source, not its exports: `appNav` appends
  // the management doors at runtime from the role, so a roleless guard run would
  // compile them away and call every surface missing.
  const railBlocks = APP_RAIL_BLOCKS.map((name) => declarationBlock(modelSrc, name));
  const unreadable = APP_RAIL_BLOCKS.filter((_, i) => railBlocks[i] === null);
  const missingDoors = findMissingDoors(railBlocks.filter(Boolean).join("\n"));

  // Rule 6 judges the folds the model already declares, so it reads the same
  // target list the dead-leaf and orphan rules read: a page that is folded under
  // a door is still in the rail, and a fold that hides a page which is not below
  // its door is a link nobody asked for.
  const folds = findBrokenFolds(targets);
  const folded = targets.filter((t) => t.depth === 2);

  // Rule 7 reads the catalogue the rail's labels come from and every source file
  // that could ask for one of them. The catalogue is `en` because that is the
  // locale the keys are authored in; whether `de` carries the same set is
  // `validate-i18n.mjs`, which `npm run test` runs as its first step.
  const catalogue = JSON.parse(await readFile(CATALOGUE, "utf8"));
  const labelSources = new Map();
  for await (const file of walkLabelSources()) {
    labelSources.set(relative(ROOT, file), await readFile(file, "utf8"));
  }
  const labels = findDeadLabels({ catalogue, sources: labelSources });

  return {
    nested,
    dead,
    orphans,
    exceptions,
    missingDoors,
    unreadable,
    folds,
    deadLabels: labels.dead,
    unreadableLabels: labels.unreadable,
    routes: routes.length,
    leaves: targets.length,
    groups: new Set(folded.map((t) => t.parent)).size,
    folded: folded.length,
    recorded: entries.length,
    labelKeys: LABELED_NAMESPACES.flatMap((ns) => leafLabelKeys(catalogue, ns)).length,
    labelFiles: labelSources.size
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
  // The list this writes excuses a route from the rail; it does not open a
  // surface. Rule 5 is not updatable — that is the point of it.
  console.log(
    `[nav-depth] merken: eine neue Fläche braucht trotzdem ein Blatt in ${APP_RAIL_BLOCKS.join(" / ")} (${SURFACE_PREFIXES.join(", ")})`
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
      .then((r) => {
        let failed = false;
        if (r.nested.length) {
          failed = true;
          console.error(
            `[nav-depth] FAILED - ${r.nested.length} layout(s) carry their own area nav:`
          );
          for (const n of r.nested) console.error(`  ${n.file}  ${n.tag}`);
          console.error(`Only ${SHELL} may. Add a section to navModel.ts instead.`);
        }
        if (r.dead.length) {
          failed = true;
          console.error(`[nav-depth] FAILED - ${r.dead.length} rail link(s) have no route:`);
          for (const d of r.dead) console.error(`  ${d}`);
        }
        if (r.orphans.length) {
          failed = true;
          console.error(`[nav-depth] FAILED - ${r.orphans.length} area(s) nobody can navigate to:`);
          for (const o of r.orphans) console.error(`  ${o}`);
          console.error("Add a leaf to navModel.ts, or --update with a reason.");
        }
        if (r.unreadable.length || r.missingDoors.length) {
          failed = true;
          for (const name of r.unreadable) {
            console.error(
              `[nav-depth] FAILED - ${name} ist in navModel.ts nicht als Array zu lesen — die Tür-Regel sieht keine Blätter`
            );
          }
          if (r.missingDoors.length) {
            console.error(
              `[nav-depth] FAILED - ${r.missingDoors.length} Fläche(n) ohne Tür im App-Rail:`
            );
            for (const p of r.missingDoors) console.error(`  ${p}`);
          }
          console.error(
            `Ein Blatt in ${APP_RAIL_BLOCKS.join(" / ")} ist der Weg hinein. Das Avatar-Menü trägt diese Links nicht mehr — eine zweite Liste mit eigener Rolle ist die Ablage, nicht der Weg.`
          );
        }
        // A recorded exception is the one finding that cannot be seen from the
        // route tree: the app still works, the reason beside it just stopped
        // being true.
        if (r.exceptions.length) {
          failed = true;
          console.error(
            `[nav-depth] FAILED - ${r.exceptions.length} aufgezeichnete Rail-Ausnahme(n) ohne gültigen Weg:`
          );
          for (const e of r.exceptions)
            console.error(
              `  ${e.path}${e.via ? `  ${e.via}` : ""} — ${UNNAVIATED_WHY[e.kind]}`
            );
          console.error(
            "[nav-depth] reachedVia auf die Datei setzen, die dorthin navigiert, oder den Eintrag löschen, wenn die Stelle jetzt im Rail liegt."
          );
        }
        // A fold is the only way a leaf stops being visible on its own, so it is
        // the one place where the rail can promise a page and hide it.
        if (r.folds.length) {
          failed = true;
          console.error(
            `[nav-depth] FAILED - ${r.folds.length} fehlerhafte Faltung(en) im Rail:`
          );
          for (const f of r.folds)
            console.error(
              `  ${f.to}${f.parent ? `  unter ${f.parent}` : ""}${f.detail ? `  children: ${f.detail}` : ""} — ${FOLD_WHY[f.kind]}`
            );
          console.error(
            "[nav-depth] Eine Gruppe hängt unter ihrer Tür: Pfad der Tür vorangestellt, die Tür selbst nicht in der Gruppe, keine Gruppe unter einer Gruppe."
          );
        }
        // A label nothing quotes is the same defect as a leaf pointing at a
        // deleted route, one layer earlier: the string stays, the thing that
        // would have shown it does not.
        if (r.deadLabels.length) {
          failed = true;
          console.error(
            `[nav-depth] FAILED - ${r.deadLabels.length} Label(s) im Rail-Framing fragt nichts:`
          );
          for (const k of r.deadLabels) console.error(`  ${k}`);
          console.error(
            "[nav-depth] Key löschen, oder das Blatt wieder hinkleben, das ihn brauchte — einen Label, den kein t() und kein labelKey nennt, sieht niemand."
          );
        }
        // The finding that means the rule did not look: a key assembled at
        // runtime matches no scan, so its namespace is declared unreadable
        // instead of being passed.
        if (r.unreadableLabels.length) {
          failed = true;
          console.error(
            `[nav-depth] FAILED - ${r.unreadableLabels.length} Label-Namespace(s) kann die Regel nicht lesen:`
          );
          for (const u of r.unreadableLabels) console.error(`  ${u.ns} — ${u.detail}`);
          console.error(
            "[nav-depth] Ein zur Laufzeit gebauter Key ist für jeden Scan tot: entweder das Wortliteral in den Quelltext, oder der Namespace raus aus LABELED_NAMESPACES — mit Grund, nicht schweigend."
          );
        }
        if (failed) process.exit(1);
        console.log(
          `[nav-depth] OK - ${r.routes} routes, ${r.leaves} rail leaves (${r.folded} in ${r.groups} Gruppe(n) gefaltet), ${SURFACE_PREFIXES.length} Flächen mit Tür, eine Nav-Liste, ${r.recorded} Ausnahme(n) mit Weg, ${r.labelKeys} Rail-Labels in ${r.labelFiles} Quellen genannt`
        );
      })
      .catch((e) => {
        console.error(e);
        process.exit(1);
      });
  }
}