#!/usr/bin/env node
/**
 * One-shot layout probe: after raising every sub-11px font to the 11px floor,
 * report text nodes that no longer fit their box.
 *
 * Overflow is the real risk of bumping font sizes, and a screenshot diff cannot
 * see it — clipped glyphs look identical to unchanged pixels at a glance.
 */
import { chromium } from "playwright";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = join(__dirname, "../..");

const base = (process.env.AGENT_E2E_BASE_URL || "http://127.0.0.1:8088").replace(/\/$/, "");

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

async function probe(page) {
  return page.evaluate(() => {
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const txt = (node.textContent || "").trim();
      if (!txt) continue;
      const el = node.parentElement;
      if (!el) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") continue;
      // sr-only is clipped to 1px on purpose; it always "overflows".
      if (el.classList?.contains("sr-only")) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;

      // Horizontal: content wider than the padding box, and not allowed to scroll/wrap.
      const overflowX = el.scrollWidth - el.clientWidth;
      const wraps = cs.whiteSpace !== "nowrap";
      const scrolls = cs.overflowX === "auto" || cs.overflowX === "scroll";
      if (overflowX > 1 && !wraps && !scrolls) {
        out.push({ kind: "h", tag: el.tagName, cls: el.className?.toString().slice(0, 70), text: txt.slice(0, 40), over: overflowX, ws: cs.whiteSpace });
      }

      // Vertical: glyphs pushed past the box while the box is height-constrained.
      const lineH = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
      const lines = Math.max(1, Math.round(r.height / lineH));
      const overflowY = el.scrollHeight - el.clientHeight;
      const vScrolls = cs.overflowY === "auto" || cs.overflowY === "scroll";
      if (overflowY > 2 && !vScrolls && cs.overflowY === "hidden") {
        out.push({ kind: "v", tag: el.tagName, cls: el.className?.toString().slice(0, 70), text: txt.slice(0, 40), over: overflowY, fs: cs.fontSize });
      }
    }
    return out;
  });
}

async function main() {
  loadDotenv(join(REPO, ".env"));
  loadDotenv(join(REPO, ".env.e2e"));
  const email = (process.env.AGENT_E2E_EMAIL || process.env.AGENT_INITIAL_ADMIN_EMAIL || "").trim();
  const password = (process.env.AGENT_E2E_PASSWORD || process.env.AGENT_INITIAL_ADMIN_PASSWORD || "").trim();

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => localStorage.setItem("agent-ui.lang", "en"));
  const page = await ctx.newPage();

  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 45000 });

  let total = 0;
  for (const route of ROUTES) {
    try {
      await page.goto(base + route, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.waitForTimeout(1200);
      const issues = await probe(page);
      total += issues.length;
      console.log(`\n=== ${route} — ${issues.length} overflow issue(s) ===`);
      const seen = new Set();
      for (const i of issues) {
        const key = `${i.kind}|${i.cls}`;
        if (seen.has(key)) continue;
        seen.add(key);
        console.log(`  [${i.kind}] <${i.tag}> .${i.cls}  over=${i.over}px  "${i.text}"`);
      }
    } catch (e) {
      console.log(`\n=== ${route} — probe error: ${String(e).slice(0, 90)} ===`);
    }
  }
  await browser.close();
  console.log(`\n[overflow-probe] total issues: ${total}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
