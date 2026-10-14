/**
 * Build crawlable /app routes from App.tsx (no hand-maintained path table).
 *
 * Scans nested <Route> trees with a brace-aware opening-tag parser so
 * `element={<Foo bar="x">…}` does not break path joining.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(__dirname, "..");
const APP_TSX = join(FRONTEND, "src/App.tsx");
const BASELINE = join(__dirname, "page-shell-baseline.json");

const SKIP_ROUTES = new Set([
  "/app/dashboard/shared",
  "/app/coding-agent",
  "/app/login",
  "/app/setup",
  "/app/*",
]);

const SKIP_COMPONENTS = new Set([
  "RestrictedNavRedirect",
  "RequireSession",
  "RequireSiteAdmin",
  "RequireOrgAdmin",
  "RequireUserAdmin",
  "RequireCapability",
  "Navigate",
  "InterfacesLayout",
  "SettingsLayout",
  "AppLayout",
  "Route",
  "DefaultLandingRedirect",
  "LegacyCodingAgentRedirect",
]);

const EXTRA_ROUTES = [
  "/app/chat",
  "/app/dashboard",
  "/app/admin/interfaces/providers",
];

function joinPath(parentAbs, seg) {
  if (!seg) return parentAbs;
  if (seg.startsWith("/")) return `/app${seg}`.replace(/\/{2,}/g, "/");
  const base = parentAbs === "/app/" ? "/app" : parentAbs.replace(/\/$/, "");
  return `${base}/${seg}`.replace(/\/{2,}/g, "/");
}

function normalizeAbs(abs) {
  if (!abs || abs === "/app") return "/app/";
  if (abs.length > 5 && abs.endsWith("/")) return abs.slice(0, -1);
  return abs;
}

function pageComponentName(jsx) {
  const names = [...jsx.matchAll(/<([A-Z][A-Za-z0-9]*)\b/g)].map((m) => m[1]);
  for (let i = names.length - 1; i >= 0; i--) {
    if (!SKIP_COMPONENTS.has(names[i])) return names[i];
  }
  return null;
}

/**
 * Find end index of a JSX opening tag starting at `<Route`, respecting `{…}` and strings.
 * Returns { end, selfClosing, attrs } where end is index after the tag.
 */
function readRouteOpenTag(src, start) {
  // start points at '<' of <Route
  let i = start + "<Route".length;
  let brace = 0;
  let quote = null;
  while (i < src.length) {
    const c = src[i];
    if (quote) {
      if (c === "\\" && quote !== "`") {
        i += 2;
        continue;
      }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      quote = c;
      i++;
      continue;
    }
    if (c === "{") {
      brace++;
      i++;
      continue;
    }
    if (c === "}") {
      brace = Math.max(0, brace - 1);
      i++;
      continue;
    }
    if (brace === 0 && c === "/" && src[i + 1] === ">") {
      return { end: i + 2, selfClosing: true, attrs: src.slice(start, i + 2) };
    }
    if (brace === 0 && c === ">") {
      return { end: i + 1, selfClosing: false, attrs: src.slice(start, i + 1) };
    }
    i++;
  }
  return { end: src.length, selfClosing: true, attrs: src.slice(start) };
}

/**
 * @returns {{ route: string, component: string|null }[]}
 */
export function parseAppRoutes(src) {
  /** @type {{ abs: string }[]} */
  const stack = [{ abs: "/app" }];
  /** @type {{ route: string, component: string|null }[]} */
  const out = [];

  let i = 0;
  while (i < src.length) {
    if (src.startsWith("</Route>", i)) {
      if (stack.length > 1) stack.pop();
      i += "</Route>".length;
      continue;
    }
    // "<Route" but not "<Routes" — require non-identifier after the word.
    if (src.startsWith("<Route", i) && !/[A-Za-z0-9_]/.test(src[i + 6] || "")) {
      const tag = readRouteOpenTag(src, i);
      const attrs = tag.attrs;
      const parentAbs = stack[stack.length - 1].abs;

      const pathM = attrs.match(/\bpath\s*=\s*["']([^"']+)["']/);
      const isIndex = /\bindex\b/.test(attrs);
      let abs = parentAbs;
      if (pathM) abs = joinPath(parentAbs, pathM[1]);
      else if (isIndex) abs = parentAbs;
      abs = normalizeAbs(abs);

      const isNavigate = /<Navigate\b/.test(attrs);
      const component = isNavigate ? null : pageComponentName(attrs);

      if (!tag.selfClosing) {
        stack.push({ abs: abs === "/app/" ? "/app" : abs });
      }

      if (!isNavigate && component && !SKIP_ROUTES.has(abs)) {
        out.push({ route: abs, component });
      }
      i = tag.end;
      continue;
    }
    i++;
  }

  const byRoute = new Map();
  for (const row of out) {
    if (SKIP_ROUTES.has(row.route)) continue;
    byRoute.set(row.route, row);
  }
  return [...byRoute.values()].sort((a, b) => a.route.localeCompare(b.route));
}

function componentToBaselineFile(component, baselineKeys) {
  const needle = `/${component}.tsx`;
  const hits = baselineKeys.filter((k) => k.endsWith(needle));
  if (hits.length === 1) return hits[0];
  return hits.find((k) => k.includes("/pages/")) || hits[0] || null;
}

/**
 * @param {{ includeUnauth?: boolean }} [opts]
 */
export function loadResponsiveRoutes(opts = {}) {
  const includeUnauth = opts.includeUnauth === true;
  const appSrc = readFileSync(APP_TSX, "utf8");
  let baseline = {};
  try {
    baseline = JSON.parse(readFileSync(BASELINE, "utf8"));
  } catch {
    baseline = {};
  }
  const baselineKeys = Object.keys(baseline);

  /** @type {Map<string, { route: string, shell: string|null, file: string|null, component: string|null }>} */
  const byRoute = new Map();

  for (const row of parseAppRoutes(appSrc)) {
    if (!includeUnauth && (row.route === "/app/login" || row.route === "/app/setup")) continue;
    let route = row.route;
    if (route.includes(":slug")) route = route.replace(":slug", "impressum");
    if (route.includes(":")) continue;

    const file = row.component ? componentToBaselineFile(row.component, baselineKeys) : null;
    const shell = file && baseline[file] ? String(baseline[file]) : null;
    byRoute.set(route, { route, shell, file, component: row.component });
  }

  for (const route of EXTRA_ROUTES) {
    if (!byRoute.has(route)) byRoute.set(route, { route, shell: null, file: null, component: null });
  }

  return [...byRoute.values()].sort((a, b) => a.route.localeCompare(b.route));
}

export { EXTRA_ROUTES, SKIP_ROUTES };
