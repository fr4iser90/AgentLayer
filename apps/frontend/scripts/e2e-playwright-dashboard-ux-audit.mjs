#!/usr/bin/env node
/**
 * Playwright: open UX-audit dashboard and screenshot every block individually.
 * Expects example/dashboard-ux-audit/dashboard.json from seed_dashboard_ux_audit.py
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

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(__dirname, "..");
const REPO = join(FRONTEND, "../..");
const OUT_DIR = join(REPO, "example/dashboard-ux-audit/screenshots");
const META_PATH = join(REPO, "example/dashboard-ux-audit/dashboard.json");

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

function creds() {
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
    console.error("[ux-audit] Missing admin credentials in .env");
    process.exit(1);
  }
  return { email, password };
}

const base = (process.env.AGENT_E2E_BASE_URL || "http://127.0.0.1:8088").replace(
  /\/$/,
  ""
);

async function login(page, email, password) {
  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), {
    timeout: 45_000,
  });
}

async function main() {
  loadDotenv(join(REPO, ".env"));
  loadDotenv(join(REPO, ".env.e2e"));
  const { email, password } = creds();

  if (!existsSync(META_PATH)) {
    console.error(`[ux-audit] Missing ${META_PATH} — run scripts/seed_dashboard_ux_audit.py first`);
    process.exit(1);
  }
  const meta = JSON.parse(readFileSync(META_PATH, "utf8"));
  const dashId = meta.dashboard_id;
  const blocks = meta.blocks || [];
  mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: process.env.E2E_HEADED !== "1" });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  await context.addInitScript(() => {
    localStorage.setItem("agent-ui.lang", "en");
  });
  const page = await context.newPage();
  const results = [];

  try {
    await login(page, email, password);
    // Skip org setup if redirected there (admin already configured).
    if (page.url().includes("/app/setup")) {
      await page.goto(`${base}/app/dashboard?id=${encodeURIComponent(dashId)}`, {
        waitUntil: "domcontentloaded",
        timeout: 90_000,
      });
    } else {
      await page.goto(`${base}/app/dashboard?id=${encodeURIComponent(dashId)}`, {
        waitUntil: "domcontentloaded",
        timeout: 90_000,
      });
    }
    // Wait until at least one block is mounted
    await page.waitForSelector("[data-block-id]", { timeout: 60_000 });
    await page.waitForTimeout(1500);

    // Full board (tall scroll capture)
    const fullPath = join(OUT_DIR, "00-full-board.png");
    await page.screenshot({ path: fullPath, fullPage: true });
    results.push({ id: "full-board", type: "page", path: fullPath, ok: true });
    console.log(`[ux-audit] OK full-board → ${fullPath}`);

    for (const b of blocks) {
      const id = b.id;
      const type = b.type;
      const sel = `[data-block-id="${id}"]`;
      const loc = page.locator(sel).first();
      const count = await loc.count();
      const shot = join(OUT_DIR, `${String(results.length).padStart(2, "0")}-${type}-${id}.png`);
      if (!count) {
        console.log(`[ux-audit] MISS ${type} ${id}`);
        results.push({ id, type, path: shot, ok: false, error: "not found" });
        continue;
      }
      await loc.scrollIntoViewIfNeeded();
      await page.waitForTimeout(400);
      // Highlight briefly for clarity
      await loc.evaluate((el) => {
        el.style.outline = "3px solid #38bdf8";
        el.style.outlineOffset = "2px";
      });
      await loc.screenshot({ path: shot });
      await loc.evaluate((el) => {
        el.style.outline = "";
        el.style.outlineOffset = "";
      });
      const box = await loc.boundingBox();
      results.push({
        id,
        type,
        path: shot,
        ok: true,
        width: box?.width ?? null,
        height: box?.height ?? null,
      });
      console.log(`[ux-audit] OK ${type} ${id} → ${shot}`);
    }
  } finally {
    await browser.close();
  }

  const summaryPath = join(REPO, "example/dashboard-ux-audit/screenshot-index.json");
  writeFileSync(summaryPath, JSON.stringify({ base, dashId, results }, null, 2) + "\n");
  const failed = results.filter((r) => !r.ok);
  console.log(
    `\n[ux-audit] ${results.length - failed.length}/${results.length} shots ok → ${OUT_DIR}`
  );
  if (failed.length) process.exit(1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
