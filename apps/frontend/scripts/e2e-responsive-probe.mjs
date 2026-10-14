#!/usr/bin/env node
/**
 * Multi-viewport responsive gate (metric-first).
 *
 * Crawls routed pages at phone / tablet / desktop and fails when the document
 * (or sticky chrome) scrolls horizontally — the reliable “bricked” signal.
 * Screenshots are optional artifacts, not the gate.
 *
 *   node scripts/e2e-responsive-probe.mjs
 *   node scripts/e2e-responsive-probe.mjs --limit 5
 *   node scripts/e2e-responsive-probe.mjs --shots fail
 *   node scripts/e2e-responsive-probe.mjs --shots all
 *   node scripts/e2e-responsive-probe.mjs --routes /app/admin/interfaces/providers
 *
 * Needs a live stack (AGENT_E2E_BASE_URL) and admin credentials.
 */
import { chromium } from "playwright";
import {
  readFileSync,
  existsSync,
  mkdirSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadResponsiveRoutes } from "./responsive-routes.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(__dirname, "..");
const REPO = join(FRONTEND, "../..");

const VIEWPORTS = [
  { id: "phone", width: 390, height: 844 },
  { id: "tablet", width: 768, height: 1024 },
  { id: "desktop", width: 1440, height: 900 },
];

const ALLOWLIST_PATH = join(__dirname, "responsive-overflow-allowlist.json");

function loadDotenv(path) {
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const i = t.indexOf("=");
    const k = t.slice(0, i).trim();
    let v = t.slice(i + 1).trim();
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    ) {
      v = v.slice(1, -1);
    }
    if (k && process.env[k] === undefined) process.env[k] = v;
  }
}

function parseArgs(argv) {
  let limit = 0;
  let shots = "none"; // none | fail | all
  /** @type {string[]} */
  const onlyRoutes = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--limit") limit = Math.max(0, Number(argv[++i]) || 0);
    else if (a === "--shots") shots = String(argv[++i] || "fail");
    else if (a === "--routes") {
      const v = String(argv[++i] || "");
      for (const r of v.split(",")) {
        const t = r.trim();
        if (t) onlyRoutes.push(t.startsWith("/app") ? t : `/app${t.startsWith("/") ? t : `/${t}`}`);
      }
    } else if (a === "--help" || a === "-h") {
      console.log(`Usage: e2e-responsive-probe.mjs [--limit N] [--shots none|fail|all] [--routes path,...]`);
      process.exit(0);
    }
  }
  if (!["none", "fail", "all"].includes(shots)) shots = "fail";
  return { limit, shots, onlyRoutes };
}

function loadAllowlist() {
  try {
    const raw = JSON.parse(readFileSync(ALLOWLIST_PATH, "utf8"));
    return new Set(Array.isArray(raw.entries) ? raw.entries : []);
  } catch {
    return new Set();
  }
}

function allowKey(route, viewport, kind) {
  return `${route}|${viewport}|${kind}`;
}

async function assertApiLogin(base, email, password) {
  // Prefer API on same origin (Vite proxies /auth → stack); fall back to :8088.
  const candidates = [
    `${base}/auth/login`,
    "http://127.0.0.1:8088/auth/login",
  ];
  let last = "";
  for (const url of candidates) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (res.ok) return;
      const detail = await res.text();
      last = `${url} → HTTP ${res.status} ${detail.slice(0, 160)}`;
      if (res.status === 401 || res.status === 403) break;
    } catch (e) {
      last = `${url} → ${e}`;
    }
  }
  throw new Error(
    `API login failed (${last}). Fix AGENT_E2E_EMAIL/PASSWORD in .env.e2e to match an admin on this stack.`
  );
}

async function login(page, base, email, password, shotDir) {
  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  const emailInput = page.locator('input[type="email"], input[name="email"]');
  try {
    await emailInput.first().waitFor({ state: "visible", timeout: 20_000 });
  } catch (e) {
    if (shotDir) {
      mkdirSync(shotDir, { recursive: true });
      await page.screenshot({ path: join(shotDir, "login-no-form.png"), fullPage: true });
    }
    const body = (await page.locator("body").innerText().catch(() => "")).slice(0, 400);
    throw new Error(`Login form not found at ${page.url()}. body="${body}" (${e})`);
  }
  await emailInput.first().fill(email);
  await page.locator('input[type="password"], input[name="password"]').first().fill(password);
  await page.locator('button[type="submit"]').click();
  try {
    await page.waitForURL((url) => !url.pathname.endsWith("/login"), {
      timeout: 30_000,
    });
  } catch (e) {
    if (shotDir) {
      mkdirSync(shotDir, { recursive: true });
      await page.screenshot({ path: join(shotDir, "login-stuck.png"), fullPage: true });
    }
    const alert = await page.locator('[role="alert"]').innerText().catch(() => "");
    throw new Error(
      `Still on login after submit. alert="${alert}" url=${page.url()} (${e})`
    );
  }
}

/**
 * Metric probe in-page: overflow + collapsed PageShell (too-narrow column).
 * Horizontal scroll alone misses the classic bug: max-w-page resolving to a
 * spacing token (40px) so content bricks into a character strip.
 */
async function measureOverflow(page) {
  return page.evaluate(() => {
    const findings = [];
    const doc = document.documentElement;
    const body = document.body;
    const pageOver = Math.max(
      (doc?.scrollWidth || 0) - (doc?.clientWidth || 0),
      (body?.scrollWidth || 0) - (body?.clientWidth || 0)
    );
    if (pageOver > 1) {
      findings.push({ kind: "page_x", over: pageOver, detail: "document horizontal scroll" });
    }

    // PageShell columns: max-w-page* must resolve to rem reading widths, not spacing.
    // shell_token catches theme collisions (max-w-page → 40px). shell_narrow catches
    // a collapsed strip; nested empty-state shells can be legitimately narrower, so
    // only fail when the box is pathologically small.
    const TOKEN_MIN_PX = {
      "max-w-pageNarrow": 700, // 48rem ≈ 768
      "max-w-page": 800, // 56rem ≈ 896
      "max-w-pageWide": 1000, // 72rem ≈ 1152
      "max-w-measure": 600,
      "max-w-dialog": 400,
    };
    const main = document.querySelector("main");
    const mainW = main ? main.getBoundingClientRect().width : window.innerWidth;
    for (const el of document.querySelectorAll("div, section, article, main")) {
      const cls = (el.className || "").toString();
      if (!cls) continue;
      let token = null;
      for (const t of Object.keys(TOKEN_MIN_PX)) {
        if (new RegExp(`(?:^|\\s)${t}(?:\\s|$)`).test(cls)) {
          token = t;
          break;
        }
      }
      if (!token) continue;
      if (!/\bmx-auto\b/.test(cls) && !/\bw-full\b/.test(cls)) continue;
      const cs = getComputedStyle(el);
      const maxW = cs.maxWidth;
      const maxPx = maxW.endsWith("px") ? parseFloat(maxW) : maxW.endsWith("rem") ? parseFloat(maxW) * 16 : NaN;
      const boxW = el.getBoundingClientRect().width;
      if (Number.isFinite(maxPx) && maxPx < (TOKEN_MIN_PX[token] || 200)) {
        findings.push({
          kind: "shell_token",
          over: Math.round(TOKEN_MIN_PX[token] - maxPx),
          detail: `${token} computed max-width=${maxW} (token collision / wrong theme)`,
        });
      }
      // Collapsed strip: ≤120px or <12% of main (the old bug was ~48px).
      if (boxW > 0 && (boxW <= 120 || boxW < mainW * 0.12)) {
        findings.push({
          kind: "shell_narrow",
          over: Math.round(Math.max(120, mainW * 0.12) - boxW),
          detail: `${token} box=${Math.round(boxW)}px main=${Math.round(mainW)}px (collapsed column)`,
        });
      }
    }

    for (const sel of ["header", "[class*='sticky']"]) {
      for (const el of document.querySelectorAll(sel)) {
        const over = el.scrollWidth - el.clientWidth;
        if (over > 1) {
          findings.push({
            kind: "chrome_x",
            over,
            detail: `${el.tagName}.${(el.className || "").toString().slice(0, 60)}`,
          });
        }
      }
    }

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    let node;
    while ((node = walker.nextNode())) {
      const txt = (node.textContent || "").trim();
      if (!txt) continue;
      const el = node.parentElement;
      if (!el) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") continue;
      if (el.classList?.contains("sr-only")) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const overflowX = el.scrollWidth - el.clientWidth;
      const wraps = cs.whiteSpace !== "nowrap";
      const scrolls = cs.overflowX === "auto" || cs.overflowX === "scroll";
      if (overflowX > 2 && !wraps && !scrolls) {
        const cls = (el.className || "").toString().slice(0, 70);
        const key = `h|${cls}`;
        if (seen.has(key)) continue;
        seen.add(key);
        findings.push({
          kind: "text_h",
          over: overflowX,
          detail: `<${el.tagName}> .${cls} "${txt.slice(0, 40)}"`,
        });
      }
    }

    // Soft: vertical hidden clips (reported, not hard-fail in v1)
    const soft = [];
    // console noise collected outside

    return { findings, soft };
  });
}

async function main() {
  loadDotenv(join(REPO, ".env"));
  loadDotenv(join(REPO, ".env.e2e"));
  const { limit, shots, onlyRoutes } = parseArgs(process.argv.slice(2));

  const base = (process.env.AGENT_E2E_BASE_URL || "http://127.0.0.1:8088").replace(/\/$/, "");
  const email = (
    process.env.AGENT_E2E_EMAIL ||
    process.env.AGENT_TEST_EMAIL ||
    process.env.AGENT_INITIAL_ADMIN_EMAIL ||
    ""
  ).trim();
  const password = (
    process.env.AGENT_E2E_PASSWORD ||
    process.env.AGENT_TEST_PASSWORD ||
    process.env.AGENT_INITIAL_ADMIN_PASSWORD ||
    ""
  ).trim();
  if (!email || !password) {
    console.error("[responsive] Missing admin credentials (AGENT_E2E_EMAIL / PASSWORD)");
    process.exit(1);
  }

  let routes = loadResponsiveRoutes({ includeUnauth: false });
  if (onlyRoutes.length) {
    routes = routes.filter((r) => onlyRoutes.includes(r.route));
    for (const r of onlyRoutes) {
      if (!routes.some((x) => x.route === r)) routes.push({ route: r, shell: null, file: null });
    }
  }
  if (limit > 0) routes = routes.slice(0, limit);

  const allow = loadAllowlist();
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const outRoot =
    process.env.RESPONSIVE_OUT_DIR ||
    join(REPO, "output/responsive", stamp);
  mkdirSync(outRoot, { recursive: true });
  const shotDir = join(outRoot, "screenshots");
  if (shots !== "none") mkdirSync(shotDir, { recursive: true });

  console.log(`[responsive] base=${base} routes=${routes.length} viewports=${VIEWPORTS.length}`);
  console.log(`[responsive] out=${outRoot}`);

  try {
    await assertApiLogin(base, email, password);
  } catch (e) {
    console.error(`[responsive] ${e}`);
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  /** @type {any[]} */
  const results = [];
  /** @type {any[]} */
  const failures = [];
  /** @type {string[]} */
  const consoleSoft = [];

  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    });
    await ctx.addInitScript(() => localStorage.setItem("agent-ui.lang", "en"));
    const page = await ctx.newPage();
    page.on("pageerror", (err) => {
      consoleSoft.push(`${vp.id}: ${String(err).slice(0, 120)}`);
    });

    try {
      await login(page, base, email, password, shotDir);
    } catch (e) {
      console.error(`[responsive] login failed on ${vp.id}: ${e}`);
      await ctx.close();
      await browser.close();
      process.exit(1);
    }

    for (const entry of routes) {
      const route = entry.route;
      const row = {
        route,
        viewport: vp.id,
        shell: entry.shell,
        ok: true,
        findings: [],
        soft: [],
        error: null,
        shot: null,
      };
      try {
        await page.goto(base + route, { waitUntil: "domcontentloaded", timeout: 45_000 });
        await page.waitForTimeout(900);
        const measured = await measureOverflow(page);
        const hard = [];
        for (const f of measured.findings || []) {
          const key = allowKey(route, vp.id, f.kind);
          if (allow.has(key)) {
            row.soft.push({ ...f, allowlisted: true });
            continue;
          }
          // text_h is soft in v1 unless --strict-text (keep hard for page_x / chrome_x)
          if (f.kind === "text_h") {
            row.soft.push(f);
            continue;
          }
          hard.push(f);
        }
        row.findings = hard;
        row.soft = [...row.soft, ...(measured.soft || [])];
        if (hard.length) {
          row.ok = false;
          failures.push(row);
        }

        const wantShot =
          shots === "all" || (shots === "fail" && !row.ok);
        if (wantShot) {
          const name = `${vp.id}__${route.replace(/\//g, "_").replace(/^_app_?/, "") || "home"}.png`;
          const path = join(shotDir, name);
          await page.screenshot({ path, fullPage: true });
          row.shot = path;
        }
      } catch (e) {
        row.ok = false;
        row.error = String(e).slice(0, 200);
        failures.push(row);
      }
      results.push(row);
      const mark = row.ok ? "ok" : "FAIL";
      const n = row.findings.length;
      console.log(
        `  [${mark}] ${vp.id.padEnd(7)} ${route}${n ? ` (+${n} overflow)` : ""}${row.error ? ` err=${row.error}` : ""}`
      );
    }
    await ctx.close();
  }

  await browser.close();

  const report = {
    stamp,
    base,
    viewports: VIEWPORTS,
    routeCount: routes.length,
    resultCount: results.length,
    failureCount: failures.length,
    softConsole: consoleSoft.slice(0, 40),
    failures,
    results,
  };
  const jsonPath = join(outRoot, "report.json");
  writeFileSync(jsonPath, JSON.stringify(report, null, 2) + "\n", "utf8");

  const mdLines = [
    `# Responsive probe — ${stamp}`,
    "",
    `| metric | value |`,
    `|---|---|`,
    `| base | ${base} |`,
    `| routes | ${routes.length} |`,
    `| cells | ${results.length} |`,
    `| failures | ${failures.length} |`,
    "",
  ];
  if (failures.length) {
    mdLines.push("## Failures", "");
    for (const f of failures) {
      mdLines.push(`### \`${f.viewport}\` ${f.route}`);
      if (f.error) mdLines.push(`- error: ${f.error}`);
      for (const x of f.findings) {
        mdLines.push(`- **${x.kind}** +${x.over}px — ${x.detail || ""}`);
      }
      if (f.shot) mdLines.push(`- shot: \`${f.shot}\``);
      mdLines.push("");
    }
    mdLines.push(
      "Allowlist a false positive: add `route|viewport|kind` to",
      "`apps/frontend/scripts/responsive-overflow-allowlist.json` → `entries`.",
      ""
    );
  } else {
    mdLines.push("All cells passed (no document/chrome horizontal overflow).", "");
  }
  const mdPath = join(outRoot, "report.md");
  writeFileSync(mdPath, mdLines.join("\n"), "utf8");

  console.log(`\n[responsive] report: ${mdPath}`);
  console.log(`[responsive] ${failures.length} failure(s) / ${results.length} cells`);
  process.exit(failures.length ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
