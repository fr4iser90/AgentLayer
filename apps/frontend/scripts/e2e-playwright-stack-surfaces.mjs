#!/usr/bin/env node
/*
 * Browser validation of the deployment-mode UI reduction.
 *
 * The unit suite (src/auth/deploymentModeUiMatrix.test.tsx) already asserts
 * the matrix against rendered components with a stubbed auth user. What it
 * cannot prove is the wiring a real browser exercises: the actual router,
 * the real /auth/me payload carrying deployment_mode, the real redirect
 * guards. A `=== "agent_system"` that leaked /org would have to be caught
 * somewhere other than a mocked component.
 *
 * Assertions are URL-first. A redirect guard's observable contract is where
 * you end up, not what text happens to render — text depends on locale and
 * on the page finishing its own async work.
 *
 * Every probe records its bounding box alongside the viewport and scroll
 * position. Without that, "element not found" from a screenshot is not a
 * finding: fullPage screenshots do not expand inner scroll containers, so
 * a control below the fold is invisible in the image while being perfectly
 * present in the DOM. The manifest carries enough to tell the two apart.
 *
 * Run inside the playwright image, e.g.:
 *   docker run --rm --network host -v "$PWD/..:/work" -w /work/apps/frontend \
 *     -e BASE_URL=http://127.0.0.1:8088 -e EMAIL=... -e PASSWORD=... \
 *     -e MODE=multi_tenant -e OUT_DIR=/work/output/stack-validation \
 *     mcr.microsoft.com/playwright:v1.49.1-noble \
 *     bash -lc 'npm install playwright@1.49.1 --no-save && node scripts/e2e-playwright-stack-surfaces.mjs'
 */

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = (process.env.BASE_URL || "http://127.0.0.1:8088").replace(/\/$/, "");
const EMAIL = process.env.EMAIL || "";
const PASSWORD = process.env.PASSWORD || "";
const MODE = process.env.MODE || "multi_tenant";
const OUT = process.env.OUT_DIR || "/tmp/stack-validation";

const VALID_MODES = ["single_user", "agent_system", "multi_tenant"];
if (!VALID_MODES.includes(MODE)) {
  console.error(`MODE must be one of ${VALID_MODES.join(", ")} (got "${MODE}")`);
  process.exit(2);
}
if (!EMAIL || !PASSWORD) {
  console.error("EMAIL and PASSWORD are required");
  process.exit(2);
}

fs.mkdirSync(OUT, { recursive: true });

/**
 * The matrix, stated once. Mirrors deploymentModeUiMatrix.test.tsx:
 *   hasOrgSurface  ⇔ multi_tenant
 *   isSingleUser   ⇔ single_user  (hides user admin + People nav + org link)
 */
const EXPECT = {
  single_user: {
    orgReachable: false,
    adminUsersReachable: false,
    peopleNav: false,
    orgMenuLink: false,
    tenantScopeOption: false,
  },
  agent_system: {
    orgReachable: false,
    adminUsersReachable: true,
    peopleNav: true,
    orgMenuLink: false,
    tenantScopeOption: false,
  },
  multi_tenant: {
    orgReachable: true,
    adminUsersReachable: true,
    peopleNav: true,
    orgMenuLink: true,
    tenantScopeOption: true,
  },
}[MODE];

const results = [];
let failed = 0;

function record(probe, ok, detail, extra = {}) {
  results.push({ probe, mode: MODE, ok, detail, ...extra });
  const mark = ok ? "PASS" : "FAIL";
  console.log(`[${mark}] ${probe} — ${detail}`);
  if (!ok) failed += 1;
}

async function shot(page, name) {
  const file = path.join(OUT, `${MODE}--${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

/**
 * Bounding box + viewport context for a selector.
 *
 * `inViewport` is deliberately about the *initial* viewport, and
 * `documentHeight` is recorded so a reviewer can see whether an element
 * was simply below the fold. A screenshot alone cannot answer that.
 */
async function probeBox(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.x),
      y: Math.round(r.y),
      width: Math.round(r.width),
      height: Math.round(r.height),
      inViewport:
        r.top >= 0 &&
        r.bottom <= window.innerHeight &&
        r.width > 0 &&
        r.height > 0,
      scrollY: Math.round(window.scrollY),
      documentHeight: Math.round(document.body.scrollHeight),
      viewportHeight: window.innerHeight,
    };
  }, selector);
}

/**
 * Case-insensitive on purpose. Several labels carry Tailwind `uppercase`
 * (AdminLayout's NavGroup, among others), and Chromium's innerText —
 * which getByText matches against — reflects text-transform. A
 * case-sensitive "People" misses the rendered "PEOPLE" and reads as a
 * missing nav entry when the entry is present and the gating logic is
 * correct.
 */
async function textPresent(page, text) {
  const found = await page.getByText(new RegExp(text, "i")).count();
  return found > 0;
}

/**
 * Bounding box of the element that actually carries a given text.
 *
 * Preferred over probing a broad container selector: a box on the first
 * matching `nav` says nothing about whether the label under test was
 * rendered, positioned, or visible.
 */
async function boxOfText(page, text) {
  const loc = page.getByText(new RegExp(text, "i")).first();
  if ((await loc.count()) === 0) return null;
  const box = await loc.boundingBox().catch(() => null);
  if (!box) return null;
  const ctx = await page
    .evaluate(() => ({
      scrollY: Math.round(window.scrollY),
      documentHeight: Math.round(document.body.scrollHeight),
      viewportHeight: window.innerHeight,
    }))
    .catch(() => ({}));
  const vp = ctx.viewportHeight || 0;
  return {
    x: Math.round(box.x),
    y: Math.round(box.y),
    width: Math.round(box.width),
    height: Math.round(box.height),
    inViewport: vp > 0 && box.y >= 0 && box.y + box.height <= vp,
    ...ctx,
  };
}

async function login(page) {
  await page.goto(`${BASE}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 30_000 }),
    page.click('button[type="submit"]'),
  ]);
}

/** Navigate and report where we actually landed.
 *
 * The router has `basename="/app"` (App.tsx), so a route requested
 * without that prefix does not hit the SPA at all — it hits the backend
 * API and returns a JSON error body while the browser stays on the same
 * URL. A pathname-only check then reads "reachable" for what is really a
 * 401 page. That is precisely how an earlier version of this probe
 * reported /admin and /org as reachable while finding no nav, no user
 * menu and no policy select: every one of those pages was
 * `{"error":"unauthorized"}` with no `#root`.
 *
 * So this asserts the SPA rendered and aborts the run if it did not —
 * every downstream assertion would otherwise be measuring an error page.
 */
async function landOn(page, route) {
  await page.goto(`${BASE}${route}`, { waitUntil: "networkidle", timeout: 45_000 });
  const landed = new URL(page.url()).pathname;
  const spa = await page.evaluate(() => {
    const root = document.getElementById("root");
    const text = document.body.innerText.trim();
    return {
      hasRoot: !!root && root.children.length > 0,
      jsonError: /^\{[\s\S]*"error"[\s\S]*\}$/.test(text),
      textLen: text.length,
      head: text.slice(0, 80),
    };
  });
  if (!spa.hasRoot || spa.jsonError) {
    throw new Error(
      `${route} did not render the SPA — got ${spa.hasRoot ? "empty #root" : "no #root"}` +
        `${spa.jsonError ? ` and a JSON error body: ${spa.head}` : ""}. ` +
        `Check the /app basename; aborting because every later probe would be measuring an error page.`,
    );
  }
  return landed;
}

async function main() {
  console.log(`base=${BASE} mode=${MODE}`);

  // Confirm the server actually reports the mode we are validating. The
  // frontend falls back to multi_tenant for an unknown value, so a
  // mis-applied mode would otherwise be validated as multi_tenant and
  // every single_user assertion would "pass" against the wrong instance.
  const loginProbe = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!loginProbe.ok) {
    console.error(`login failed: HTTP ${loginProbe.status}`);
    process.exit(1);
  }
  const token = (await loginProbe.json()).access_token;
  const me = await (
    await fetch(`${BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
  ).json();
  const serverMode = String(me.deployment_mode || "").toLowerCase();
  record(
    "server reports the expected deployment_mode",
    serverMode === MODE,
    `GET /auth/me -> ${serverMode}, expected ${MODE}`,
  );
  if (serverMode !== MODE) {
    // Everything below would be measured against the wrong surface.
    console.error("deployment mode mismatch — aborting before UI probes");
    writeManifest();
    process.exit(1);
  }

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const fatal = [];
  page.on("pageerror", (e) => {
    const msg = String(e.message || e);
    if (/TypeError|ReferenceError|is not defined|is not a function/.test(msg)) fatal.push(msg);
  });

  try {
    await login(page);
    // Force English so the nav-text assertions do not depend on browser locale.
    await page.evaluate(() => localStorage.setItem("agent-ui.lang", "en"));

    // ── /org reachability ──
    const orgLanded = await landOn(page, "/app/org/knowledge");
    const orgReached = orgLanded.startsWith("/app/org");
    record(
      "/org/knowledge reachability",
      orgReached === EXPECT.orgReachable,
      `landed on ${orgLanded}, expected orgReachable=${EXPECT.orgReachable}`,
      { screenshot: await shot(page, "org-knowledge"), landed: orgLanded },
    );

    // ── /admin/users reachability ──
    const usersLanded = await landOn(page, "/app/admin/users");
    const usersReached = usersLanded === "/app/admin/users";
    record(
      "/admin/users reachability",
      usersReached === EXPECT.adminUsersReachable,
      `landed on ${usersLanded}, expected adminUsersReachable=${EXPECT.adminUsersReachable}`,
      { screenshot: await shot(page, "admin-users"), landed: usersLanded },
    );

    // ── Admin sidebar People group ──
    await landOn(page, "/app/admin");
    const peoplePresent = await textPresent(page, "People");
    // The rendered label as the browser sees it. It carries the CSS
    // text-transform, which is exactly what getByText matches against,
    // so recording it makes a case-mismatch visible in the manifest
    // instead of showing up as an unexplained absence.
    const peopleText = peoplePresent
      ? await page.getByText(/people/i).first().innerText().catch(() => "")
      : "";
    const peopleBox = peoplePresent ? await boxOfText(page, "People").catch(() => null) : null;
    record(
      "admin sidebar People group",
      peoplePresent === EXPECT.peopleNav,
      `"People" in admin nav = ${peoplePresent} (rendered as ${JSON.stringify(peopleText)}), expected ${EXPECT.peopleNav}`,
      {
        screenshot: await shot(page, "admin-nav"),
        box: peopleBox,
        renderedText: peopleText,
        note: peoplePresent
          ? ""
          : "absent from DOM — not a scroll artifact, count() is DOM-based not pixel-based",
      },
    );

    // ── User dropdown organization link ──
    // <UserMenu/> is rendered only by AppLayout, not AdminLayout, so this
    // has to run from an app route — from /app/admin there is no trigger
    // to click at all.
    await landOn(page, "/app/dashboard");
    // The trigger is the avatar button, which carries no aria-label. The
    // earlier selector (`header button:last-of-type`) landed on the
    // notification bell instead, so the menu never opened and the link
    // read as absent when nothing had been measured. UserMenu sets
    // `title={email}` on the trigger and renders the link as
    // `role="menuitem"` pointing at /org, so both the open state and the
    // link are checked structurally rather than by visible text.
    const trigger = page.locator(`button[aria-haspopup="menu"][title="${EMAIL}"]`).first();
    let menuOpened = false;
    let orgLinkPresent = false;
    if ((await trigger.count()) > 0) {
      await trigger.click();
      await page.waitForTimeout(500);
      menuOpened = (await trigger.getAttribute("aria-expanded")) === "true";
      if (menuOpened) {
        const hrefHits = await page
          .locator('a[role="menuitem"][href$="/app/org"], a[role="menuitem"][href$="/org"]')
          .count();
        const textHits = await page.locator('[role="menu"]').getByText(/organization/i).count();
        orgLinkPresent = hrefHits > 0 || textHits > 0;
      }
    }
    record(
      "user menu Organization link",
      menuOpened && orgLinkPresent === EXPECT.orgMenuLink,
      menuOpened
        ? `menu opened, orgLink=${orgLinkPresent}, expected ${EXPECT.orgMenuLink}`
        : `inconclusive — user menu never opened (no trigger matched title="${EMAIL}")`,
      { screenshot: await shot(page, "user-menu"), menuOpened },
    );

    // ── Agent policy tenant scope option ──
    // The scope <select> is gated behind a loaded agent detail
    // (AdminAgents.tsx wraps the block on `detail?.governance`) and the
    // page only auto-selects an agent when the list is non-empty. A zero
    // count therefore has two unrelated causes — nothing selected,
    // versus the tenant option genuinely hidden by the mode — and the
    // probe must not report the second when it measured the first.
    await landOn(page, "/app/admin/agents");
    const policySelect = page.locator('select:has(option[value="global"])');
    let selectAttached = false;
    try {
      await policySelect.first().waitFor({ state: "attached", timeout: 15_000 });
      selectAttached = true;
    } catch {
      selectAttached = false;
    }
    const tenantOption = selectAttached
      ? await page
          .locator('select option[value="tenant"], [role="option"][value="tenant"]')
          .count()
      : null;
    const conclusive = tenantOption !== null;
    record(
      "agent policy tenant scope option",
      conclusive && (tenantOption > 0) === EXPECT.tenantScopeOption,
      conclusive
        ? `tenant option count=${tenantOption}, expected present=${EXPECT.tenantScopeOption}`
        : `inconclusive — policy scope <select> never rendered, so the option count was never measurable (no agent selected; agent list likely empty). Expected present=${EXPECT.tenantScopeOption}`,
      { screenshot: await shot(page, "admin-agents"), conclusive, selectAttached },
    );

    // ── Core surfaces render without fatal JS, in this mode ──
    for (const route of ["/app/dashboard", "/app/chat", "/app/settings/friends", "/app/settings/shares"]) {
      const landed = await landOn(page, route);
      const bodyLen = await page.evaluate(() => document.body.innerText.trim().length);
      record(
        `renders ${route}`,
        bodyLen > 40,
        `landed ${landed}, body text ${bodyLen} chars`,
        { screenshot: await shot(page, `route${route.replace(/\//g, "_")}`) },
      );
    }
  } finally {
    await browser.close();
    writeManifest(fatal);
  }

  if (fatal.length) {
    console.log(`[FAIL] fatal JS errors: ${fatal.length}`);
    fatal.slice(0, 5).forEach((m) => console.log(`       ${m.slice(0, 160)}`));
    failed += 1;
  } else {
    console.log("[PASS] no fatal JS errors");
  }

  console.log(`\nmode ${MODE}: ${results.filter((r) => r.ok).length}/${results.length} probes passed`);
  process.exit(failed ? 1 : 0);
}

function writeManifest(fatal = []) {
  const file = path.join(OUT, `manifest--${MODE}.json`);
  fs.writeFileSync(
    file,
    JSON.stringify(
      {
        mode: MODE,
        base: BASE,
        generatedAt: new Date().toISOString(),
        expectation: EXPECT,
        probes: results,
        fatalJsErrors: fatal,
        failed,
      },
      null,
      2,
    ),
  );
  console.log(`manifest: ${file}`);
}

main().catch((e) => {
  console.error("runner error:", e);
  writeManifest();
  process.exit(1);
});
