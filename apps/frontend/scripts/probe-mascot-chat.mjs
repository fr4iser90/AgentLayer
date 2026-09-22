// Seeds a chat thread into localStorage so the assistant turn (and its Volt
// mascot) renders without needing a live agent run.
// Run through the gate:  ./scripts/e2e-probe.sh probe-mascot-chat.mjs
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = "/work/output/mascot-live";
const PREFIX = "agent-layer.chat.v1:";

const email = (process.env.AGENT_E2E_EMAIL || process.env.AGENT_INITIAL_ADMIN_EMAIL || "").trim();
const password = (
  process.env.AGENT_E2E_PASSWORD || process.env.AGENT_INITIAL_ADMIN_PASSWORD || ""
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

const now = () => Date.now();

(async () => {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));

  await login(page);
  await page.waitForTimeout(1200);

  // Discover the per-user storage key the app already uses.
  const keys = await page.evaluate(() => Object.keys(localStorage));
  console.log("localStorage keys:", JSON.stringify(keys));

  let chatKey = keys.find((k) => k.startsWith(PREFIX));
  if (!chatKey) {
    // Fall back to guessing the user id from any key that looks like it carries one.
    const guess = keys.find((k) => /user|sub|email/i.test(k));
    console.log("no chat key yet; candidate for user id:", guess);
    chatKey = null;
  }

  const seeded = {
    version: 1,
    activeThreadId: "probe-thread",
    threads: [
      {
        id: "probe-thread",
        title: "Mascot probe",
        mode: "chat",
        model: "probe-model",
        updatedAt: now(),
        messages: [
          { role: "user", content: "Zeig mir mal deine States.", createdAt: now() - 60000, id: "m1" },
          {
            role: "assistant",
            content:
              "Klar. Ich bin Volt und laufe über denselben Treiber wie die anderen 27 States — " +
              "der Agent-Status steuert nur die Pose, die Zeichnung bleibt gleich.",
            reasoningContent: "Der Nutzer will die States sehen. Ich antworte und bleibe dabei sichtbar.",
            createdAt: now() - 30000,
            id: "m2",
          },
        ],
      },
    ],
  };

  // Write under every plausible key so we hit whichever the app reads.
  await page.evaluate(
    ([prefix, payload, existing]) => {
      const targets = existing ? [existing] : [`${prefix}probe`];
      targets.forEach((k) => localStorage.setItem(k, JSON.stringify(payload)));
    },
    [PREFIX, seeded, chatKey]
  );
  console.log("seeded into:", chatKey || `${PREFIX}probe`);

  await page.goto(`${base}/app/chat`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);

  const rigs = await page.evaluate(() => {
    const svgs = [...document.querySelectorAll('svg[role="img"]')];
    return svgs.map((s) => {
      const r = s.getBoundingClientRect();
      return { label: s.getAttribute("aria-label"), w: Math.round(r.width), h: Math.round(r.height) };
    });
  });
  console.log("chat rigs:", JSON.stringify(rigs));

  await page.screenshot({ path: `${OUT}/chat-seeded.png` });
  const bubble = page.locator("li").filter({ hasText: "Volt" }).last();
  if (await bubble.count()) {
    await bubble.screenshot({ path: `${OUT}/chat-bubble.png` });
  }
  console.log("errors:", errors.length);
  errors.slice(0, 10).forEach((e) => console.log("  " + e));
  await browser.close();
})().catch((e) => {
  console.error("PROBE FAILED:", e.message);
  process.exit(1);
});
