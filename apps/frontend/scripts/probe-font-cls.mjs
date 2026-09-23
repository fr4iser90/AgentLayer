#!/usr/bin/env node
/**
 * Font-and-shift probe: does the webfont actually paint, and what does the swap
 * cost in layout shift?
 *
 * Answers three things that a build log cannot:
 *   1. Is rendered text actually IBM Plex, or silently the fallback?
 *   2. Which font files did the browser really fetch, and when?
 *   3. What is the Cumulative Layout Shift across the swap window?
 *
 * CLS is read from PerformanceObserver('layout-shift'), which is the same
 * source Chrome DevTools uses. Input-free shifts only, matching how the metric
 * is defined.
 */
import { chromium } from "playwright";
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = join(__dirname, "../..");
const base = (process.env.AGENT_E2E_BASE_URL || "http://[::1]:4173").replace(/\/$/, "");

function loadDotenv(path) {
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const i = t.indexOf("=");
    const k = t.slice(0, i).trim();
    let v = t.slice(i + 1).trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    if (k && process.env[k] === undefined) process.env[k] = v;
  }
}

function resolveChromium() {
  if (process.env.CHROMIUM_PATH && existsSync(process.env.CHROMIUM_PATH)) return process.env.CHROMIUM_PATH;
  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    join(process.env.HOME || "", ".cache/ms-playwright"),
  ].filter(Boolean);
  for (const root of roots) {
    if (!existsSync(root)) continue;
    const builds = readdirSync(root)
      .filter((d) => /^chromium-\d+$/.test(d))
      .sort((a, b) => parseInt(b.split("-")[1], 10) - parseInt(a.split("-")[1], 10));
    for (const build of builds) {
      for (const dir of ["chrome-linux64", "chrome-linux"]) {
        const p = join(root, build, dir, "chrome");
        if (existsSync(p)) return p;
      }
    }
  }
  return undefined;
}

const ROUTES = ["/app/dashboard", "/app/chat", "/app/settings", "/app/admin/users"];

// Runs the whole login + route walk in its own browser. `blockFonts` gives the
// fallback-only control: without it a large CLS cannot be attributed, because an
// async table render shifts about as much as a font swap does and the remedy for
// each is the opposite of the other.
async function run({ creds, blockFonts, routes }) {
  const browser = await chromium.launch({ headless: true, executablePath: resolveChromium() });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => localStorage.setItem("agent-ui.lang", "en"));

  const page = await ctx.newPage();
  if (blockFonts) await page.route("**/*.woff2", (r) => r.abort());
  await page.addInitScript(() => {
    window.__cls = 0;
    window.__shifts = [];
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.hadRecentInput) continue;
        window.__cls += e.value;
        const src = (e.sources || [])
          .map((s) => {
            const n = s.node;
            if (!n) return null;
            const cls = typeof n.className === "string" ? n.className.slice(0, 70) : "";
            const tag = n.tagName ? n.tagName.toLowerCase() : "?";
            const prev = s.previousRect
              ? `${Math.round(s.previousRect.y)}->${Math.round(s.currentRect.y)} dy`
              : "";
            return `${tag}.${cls.replace(/\s+/g, ".")} ${prev}`;
          })
          .filter(Boolean)
          .slice(0, 3);
        window.__shifts.push({ value: +e.value.toFixed(5), at: Math.round(e.startTime), src });
      }
    }).observe({ type: "layout-shift", buffered: true });
  });

  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(creds.email);
  await page.locator('input[type="password"]').fill(creds.password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 45000 });

  const out = {};
  for (const route of routes) {
    await page.goto(base + route, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(2500);
    // addInitScript re-runs on every navigation, so __cls restarts at zero and
    // each figure is that navigation's own shift, not a running total.
    out[route] = await page.evaluate(() => ({
      cls: window.__cls,
      shifts: window.__shifts,
      family: getComputedStyle(document.body).fontFamily.split(",")[0].replace(/"/g, ""),
      plex: document.fonts.check('16px "IBM Plex Sans"'),
    }));
  }
  await browser.close();
  return out;
}

async function main() {
  loadDotenv(join(REPO, ".env"));
  const email = (process.env.AGENT_E2E_EMAIL || process.env.AGENT_INITIAL_ADMIN_EMAIL || "").trim();
  const password = (process.env.AGENT_E2E_PASSWORD || process.env.AGENT_INITIAL_ADMIN_PASSWORD || "").trim();
  const executablePath = resolveChromium();
  if (!email || !password || !executablePath) {
    console.error("[font] missing credentials or chromium");
    process.exit(2);
  }

  if (process.argv.includes("--compare")) {
    const only = process.argv.slice(2).find((a) => a.startsWith("/"));
    const routes = only ? [only] : ROUTES;
    const creds = { email, password };
    console.log("=== CLS-Isolation: mit Font vs. ohne Font ===");
    const withFont = await run({ creds, blockFonts: false, routes });
    const noFont = await run({ creds, blockFonts: true, routes });
    for (const route of routes) {
      const a = withFont[route];
      const b = noFont[route];
      const delta = a.cls - b.cls;
      const share = a.cls > 0 ? (delta / a.cls) * 100 : 0;
      console.log(`\n  ${route}`);
      console.log(`    mit Font   CLS=${a.cls.toFixed(5)}  family=${a.family}  plex=${a.plex}`);
      console.log(`    ohne Font  CLS=${b.cls.toFixed(5)}  family=${b.family}  plex=${b.plex}`);
      console.log(`    Font-Anteil ${delta.toFixed(5)}  (${share.toFixed(1)} % der Verschiebung)`);
      if (share < 15) {
        console.log("    -> NICHT der Font. Das sind Daten/Rendering, nicht Typografie.");
      } else if (share > 60) {
        console.log("    -> hauptsachlich der Font. Fallback-Metriken (size-adjust) sind das Mittel.");
      } else {
        console.log("    -> gemischt: Font und Daten tragen beide bei.");
      }
      const big = [...a.shifts].sort((x, y) => y.value - x.value)[0];
      if (big && big.value > 0.01) {
        console.log(`    groesster Shift ${big.value} @ ${big.at}ms:`);
        for (const s of big.src ?? []) console.log(`      ${s}`);
      }
    }
    return;
  }

  const browser = await chromium.launch({ headless: true, executablePath });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => localStorage.setItem("agent-ui.lang", "en"));

  // Start observing layout shifts before any navigation.
  const page = await ctx.newPage();
  await page.addInitScript(() => {
    window.__cls = 0;
    window.__shifts = [];
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.hadRecentInput) continue;
        window.__cls += e.value;
        window.__shifts.push({ value: +e.value.toFixed(5), at: Math.round(e.startTime) });
      }
    }).observe({ type: "layout-shift", buffered: true });
  });

  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 45000 });

  // Is the webfont actually loaded and used?
  const fontState = await page.evaluate(async () => {
    await document.fonts.ready;
    const loaded = [...document.fonts].map((f) => ({
      family: f.family,
      weight: f.weight,
      status: f.status,
    }));
    const probe = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const cs = getComputedStyle(el);
      return { sel, family: cs.fontFamily.split(",")[0], size: cs.fontSize };
    };
    return {
      loaded,
      bodyFamily: getComputedStyle(document.body).fontFamily,
      heading: probe("h1, h2, [class*='text-display']"),
      check: document.fonts.check('16px "IBM Plex Sans"'),
      checkMono: document.fonts.check('14px "IBM Plex Mono"'),
    };
  });

  console.log("=== Font-Status ===");
  console.log("body font-family:", fontState.bodyFamily);
  console.log("document.fonts.check('IBM Plex Sans'):", fontState.check);
  console.log("document.fonts.check('IBM Plex Mono'):", fontState.checkMono);
  console.log("geladene Faces:");
  for (const f of fontState.loaded) console.log(`  ${f.family} w${f.weight} → ${f.status}`);

  // Which font files were actually requested?
  const fontRequests = await page.evaluate(() =>
    performance
      .getEntriesByType("resource")
      .filter((e) => /\.woff2?($|\?)/.test(e.name))
      .map((e) => ({
        name: e.name.split("/").pop(),
        start: Math.round(e.startTime),
        dur: Math.round(e.duration),
        bytes: e.transferSize,
      }))
  );
  console.log("\n=== Font-Requests (this page) ===");
  for (const r of fontRequests) console.log(`  ${r.name}  start=${r.start}ms dur=${r.dur}ms ${r.bytes}B`);

  console.log("\n=== CLS pro Route ===");
  let worst = 0;
  for (const route of ROUTES) {
    await page.goto(base + route, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(2500);
    const { cls, shifts } = await page.evaluate(() => ({
      cls: window.__cls,
      shifts: window.__shifts,
    }));
    worst = Math.max(worst, cls);
    const flag = cls <= 0.1 ? "GOOD" : cls <= 0.25 ? "NEEDS-IMPROVEMENT" : "POOR";
    console.log(`  ${route.padEnd(22)} CLS=${cls.toFixed(5)}  ${flag}  (${shifts.length} shift(s))`);
    for (const s of shifts.slice(0, 4)) console.log(`      shift ${s.value} @ ${s.at}ms`);
  }
  console.log(`\n  worst CLS across routes: ${worst.toFixed(5)}  (Budget: <= 0.02)`);
  console.log(
    worst <= 0.02
      ? "  → innerhalb Budget"
      : `  → ueber Budget um ${(worst - 0.02).toFixed(5)} — fallback size-adjust noetig`
  );

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
