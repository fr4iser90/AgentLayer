#!/usr/bin/env node
/**
 * Surface-and-ink histogram.
 *
 * Counting how many times a token class appears says nothing about how much of
 * the screen it paints: one full-bleed container counts as 1, a list of 200
 * chips counts as 200. This measures the thing that is actually looked at.
 *
 * Method: sample a grid of points over the viewport, take the topmost element at
 * each point via elementFromPoint, and walk up until a non-transparent
 * background is found — that is the colour actually painted under that pixel.
 * Overlapping layers therefore cannot double-count, which a bounding-box sum
 * would do.
 *
 * Text is measured separately, over leaf text elements only, bucketed by the
 * computed `color` so raw Tailwind tones and `ink-*` tokens land in different
 * buckets.
 */
import { chromium } from "playwright";
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The pinned playwright build asks for a browser revision that is not installed
 * here: PLAYWRIGHT_BROWSERS_PATH points at a nix store entry whose chromium dir
 * is an empty stub. Resolve a real binary from the ms-playwright cache instead,
 * newest build first, tolerating both the old `chrome-linux` and the new
 * `chrome-linux64` layout.
 */
function resolveChromium() {
  if (process.env.CHROMIUM_PATH && existsSync(process.env.CHROMIUM_PATH)) {
    return process.env.CHROMIUM_PATH;
  }
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

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = join(__dirname, "../..");
const base = (process.env.AGENT_E2E_BASE_URL || "http://127.0.0.1:8088").replace(/\/$/, "");

const ROUTES = [
  "/app/dashboard",
  "/app/chat",
  "/app/schedules",
  "/app/projects",
  "/app/settings",
  "/app/admin/users",
  "/app/admin/agents",
  "/app/admin/benchmarks",
  "/app/admin/tools",
];

// Token ladder, as defined in tailwind.config.js.
const LADDER = {
  "rgb(11, 12, 14)": "canvas",
  "rgb(21, 24, 29)": "panel",
  "rgb(30, 34, 42)": "card",
  "rgb(42, 47, 57)": "raised",
  "rgb(15, 18, 24)": "field",
};

const INK = {
  "rgb(232, 234, 237)": "ink-primary",
  "rgb(180, 186, 196)": "ink-secondary",
  "rgb(163, 169, 180)": "ink-muted",
  "rgb(110, 118, 130)": "ink-faint",
  "rgb(8, 9, 11)": "ink-on-fill",
};

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

async function sample(page) {
  return page.evaluate(
    ([ladder, ink]) => {
      const surface = {};
      const text = {};
      const STEP = 8;
      const W = window.innerWidth;
      const H = window.innerHeight;
      let sampled = 0;

      for (let y = STEP / 2; y < H; y += STEP) {
        for (let x = STEP / 2; x < W; x += STEP) {
          sampled += 1;
          const el = document.elementFromPoint(x, y);
          if (!el) continue;
          // Walk up to the element that actually paints a background here.
          let node = el;
          let painted = null;
          let hops = 0;
          while (node && node !== document.documentElement && hops < 12) {
            const bg = getComputedStyle(node).backgroundColor;
            const m = bg.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)$/);
            if (m) {
              const alpha = m[4] === undefined ? 1 : parseFloat(m[4]);
              if (alpha > 0.85) {
                painted = `rgb(${m[1]}, ${m[2]}, ${m[3]})`;
                break;
              }
            }
            node = node.parentElement;
            hops += 1;
          }
          const key = painted ?? "transparent/gradient";
          const label = ladder[key] ?? `off-ladder ${key}`;
          surface[label] = (surface[label] || 0) + 1;
        }
      }

      // Text: leaf elements only, so nested spans do not double-count.
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
      let node;
      while ((node = walker.nextNode())) {
        const own = Array.from(node.childNodes)
          .filter((n) => n.nodeType === 3)
          .map((n) => n.textContent.trim())
          .join("")
          .trim();
        if (!own) continue;
        const cs = getComputedStyle(node);
        if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") continue;
        if (node.classList?.contains("sr-only")) continue;
        const r = node.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) continue;
        const area = Math.round(r.width * Math.min(r.height, parseFloat(cs.fontSize) * 2.2));
        // A near-opaque rgba of a token colour IS that token; only a real
        // translucent layer should land in its own bucket. Without this,
        // rgba(163,169,180,.9) — ink-muted — counted as off-token.
        const cm = cs.color.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)$/);
        const opaque = cm && (cm[4] === undefined || parseFloat(cm[4]) >= 0.85);
        const norm = opaque ? `rgb(${cm[1]}, ${cm[2]}, ${cm[3]})` : cs.color;
        const key = ink[norm] ?? `off-token ${norm}`;
        text[key] = (text[key] || 0) + area;
      }

      return { surface, text, sampled };
    },
    [LADDER, INK]
  );
}

function pct(n, d) {
  return d ? `${((n / d) * 100).toFixed(1)}%` : "0%";
}

/**
 * Report the on-token share from the buckets that are actually on-token.
 *
 * An earlier version subtracted only the transparent bucket here, which printed
 * "100.0% on-token" on a route where the real figure was 42.5%. A header that
 * reads green while the rows read red is worse than no header.
 */
function report(title, buckets, total, onNames) {
  const on = Object.entries(buckets)
    .filter(([k]) => onNames.includes(k))
    .reduce((n, [, v]) => n + v, 0);
  console.log(`\n  ${title} — ${pct(on, total)} on-token (${on}/${total})`);
  const rows = Object.entries(buckets).sort((a, b) => b[1] - a[1]);
  for (const [k, v] of rows.slice(0, 12)) {
    const isOn = onNames.includes(k);
    console.log(`    ${isOn ? "ON " : "off"} ${k.padEnd(34)} ${String(v).padStart(9)}  ${pct(v, total)}`);
  }
  if (rows.length > 12) console.log(`    … +${rows.length - 12} more buckets`);
}

async function main() {
  loadDotenv(join(REPO, ".env"));
  loadDotenv(join(__dirname, "../.env.e2e"));
  const email = (process.env.AGENT_E2E_EMAIL || process.env.AGENT_INITIAL_ADMIN_EMAIL || "").trim();
  const password = (process.env.AGENT_E2E_PASSWORD || process.env.AGENT_INITIAL_ADMIN_PASSWORD || "").trim();
  if (!email || !password) {
    console.error("[histogram] no credentials — set AGENT_E2E_EMAIL / AGENT_E2E_PASSWORD");
    process.exit(2);
  }

  const executablePath = resolveChromium();
  if (!executablePath) {
    console.error("[histogram] no chromium binary found — set CHROMIUM_PATH");
    process.exit(2);
  }
  const browser = await chromium.launch({ headless: true, executablePath });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => localStorage.setItem("agent-ui.lang", "en"));
  const page = await ctx.newPage();

  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 45000 });

  const aggSurface = {};
  const aggText = {};
  let aggSampled = 0;

  for (const route of ROUTES) {
    try {
      await page.goto(base + route, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.waitForTimeout(1500);
      const { surface, text, sampled } = await sample(page);
      aggSampled += sampled;
      for (const [k, v] of Object.entries(surface)) aggSurface[k] = (aggSurface[k] || 0) + v;
      for (const [k, v] of Object.entries(text)) aggText[k] = (aggText[k] || 0) + v;
      const onSurf = Object.entries(surface)
        .filter(([k]) => Object.values(LADDER).includes(k))
        .reduce((n, [, v]) => n + v, 0);
      console.log(`\n=== ${route} — surface on-token ${pct(onSurf, sampled)} ===`);
      report("SURFACE", surface, sampled, Object.values(LADDER));
      const onText = Object.entries(text)
        .filter(([k]) => Object.values(INK).includes(k))
        .reduce((n, [, v]) => n + v, 0);
      const textTotal = Object.values(text).reduce((n, v) => n + v, 0) || 1;
      report(`INK (text area ${textTotal}px²)`, text, textTotal, Object.values(INK));
      console.log(`    ink on-token: ${pct(onText, textTotal)}`);
    } catch (e) {
      console.log(`\n=== ${route} — error: ${String(e).slice(0, 100)} ===`);
    }
  }

  await browser.close();

  const surfOn = Object.entries(aggSurface)
    .filter(([k]) => Object.values(LADDER).includes(k))
    .reduce((n, [, v]) => n + v, 0);
  const textTotal = Object.values(aggText).reduce((n, v) => n + v, 0) || 1;
  const inkOn = Object.entries(aggText)
    .filter(([k]) => Object.values(INK).includes(k))
    .reduce((n, [, v]) => n + v, 0);

  console.log("\n\n########## AGGREGATE ##########");
  report("SURFACE (all routes)", aggSurface, aggSampled || 1, Object.values(LADDER));
  console.log(`\n  SURFACE on-token: ${pct(surfOn, aggSampled || 1)}  (${surfOn}/${aggSampled} samples)`);
  report("INK (all routes)", aggText, textTotal, Object.values(INK));
  console.log(`\n  INK on-token: ${pct(inkOn, textTotal)}  (${inkOn}/${textTotal}px²)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
