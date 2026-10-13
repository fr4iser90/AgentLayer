// Visual check of the mascot integration in the running app.
// Run through the gate:  ./scripts/e2e-probe.sh probe-mascot-live.mjs
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = "/work/output/mascot-live";

const email = (
  process.env.AGENT_E2E_EMAIL ||
  process.env.AGENT_INITIAL_ADMIN_EMAIL ||
  ""
).trim();
const password = (
  process.env.AGENT_E2E_PASSWORD ||
  process.env.AGENT_INITIAL_ADMIN_PASSWORD ||
  ""
).trim();
const base = (process.env.AGENT_E2E_BASE_URL || "http://127.0.0.1:8088").replace(/\/$/, "");

async function login(page) {
  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"], input[name="email"]').first().fill(email);
  await page.locator('input[type="password"]').first().fill(password);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 20000 }),
    page.locator('button[type="submit"]').first().click(),
  ]);
}

/**
 * Count mascot rigs actually mounted. Keyed on the rig's own defs signature,
 * not on role="img": the accessible name lives on the wrapper span and the SVG
 * itself is aria-hidden.
 */
async function countRigs(page) {
  return page.evaluate(() => {
    const svgs = [...document.querySelectorAll("svg")].filter((s) => {
      const d = s.querySelector("defs");
      return d && [...d.children].some((c) => /-g$|-halo$/.test(c.id || ""));
    });
    return {
      rigs: svgs.length,
      owners: svgs.map((s) => {
        const host = s.closest('[role="img"]');
        const r = s.getBoundingClientRect();
        return {
          label: host ? host.getAttribute("aria-label") : null,
          size: `${Math.round(r.width)}x${Math.round(r.height)}`,
        };
      }),
    };
  });
}

(async () => {
  if (!email || !password) {
    console.error("no credentials in env");
    process.exit(1);
  }
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console: ${m.text()}`);
  });

  await login(page);
  await page.waitForTimeout(1500);

  const header = await countRigs(page);
  console.log("header rigs:", JSON.stringify(header));
  await page.locator("header").screenshot({ path: `${OUT}/header.png` });

  // Close-up of the user avatar button in the top-right cluster.
  const avatar = page.locator("header button[aria-haspopup='menu']").last();
  if (await avatar.count()) {
    await avatar.screenshot({ path: `${OUT}/usermenu-closed.png` });
    await avatar.click();
    await page.waitForTimeout(600);
    await avatar.screenshot({ path: `${OUT}/usermenu-open.png` });
    const openRigs = await countRigs(page);
    console.log("after opening menu:", JSON.stringify(openRigs));
    await page.keyboard.press("Escape");
  }

  for (const route of ["/app/chat", "/app/dashboard"]) {
    await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1800);
    const rigs = await countRigs(page);
    console.log(`${route} rigs:`, JSON.stringify(rigs));
    await page.screenshot({ path: `${OUT}${route.replace("/app", "")}.png` });
  }

  console.log("errors:", errors.length);
  errors.slice(0, 15).forEach((e) => console.log("  " + e));
  await browser.close();
})().catch((e) => {
  console.error("PROBE FAILED:", e.message);
  process.exit(1);
});
