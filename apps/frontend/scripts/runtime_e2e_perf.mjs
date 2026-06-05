#!/usr/bin/env node
/**
 * Browser E2E runtime perf — measures real page load / spinner / API timings.
 * Invoked by scripts/diag/runtime_e2e_perf.py (not part of the app).
 *
 * Env: AGENT_E2E_BASE_URL, AGENT_INITIAL_ADMIN_* or AGENT_E2E_*
 * Output: single JSON line prefixed with __RUNTIME_E2E_JSON__
 */
import { chromium } from "playwright";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = join(__dirname, "../../..");

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
  if (!email || !password) return null;
  return { email, password };
}

const base = (process.env.AGENT_E2E_BASE_URL || "http://127.0.0.1:8088").replace(
  /\/$/,
  ""
);

const AUTH_API = ["/auth/setup-status", "/auth/refresh", "/auth/login"];

function nowMs() {
  return Date.now();
}

function summarizeApiCalls(entries) {
  const rows = [];
  for (const e of entries) {
    const url = e.url || "";
    if (!AUTH_API.some((p) => url.includes(p)) && !url.includes("/v1/dashboards")) {
      continue;
    }
    const path = url.replace(base, "").split("?")[0];
    rows.push({
      path,
      method: e.method || "GET",
      ms: Math.round(e.duration || 0),
      status: e.status ?? null,
    });
  }
  rows.sort((a, b) => b.ms - a.ms);
  return rows;
}

function attachNetwork(page) {
  const entries = [];
  page.on("response", async (response) => {
    try {
      const req = response.request();
      const url = req.url();
      if (!url.startsWith(base)) return;
      const timing = req.timing();
      const start = timing.startTime || 0;
      const end = timing.responseEnd || timing.responseStart || 0;
      const duration = end > 0 && start >= 0 ? end - start : 0;
      entries.push({
        url,
        method: req.method(),
        duration,
        status: response.status(),
      });
    } catch {
      /* ignore */
    }
  });
  return entries;
}

async function waitUntilNotAuthLoading(page, timeoutMs) {
  const t0 = nowMs();
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText || "";
      const loading =
        text.includes("Wird geladen") ||
        text.includes("Loading…") ||
        text.includes("Loading...");
      const redirected =
        location.pathname.includes("/login") ||
        location.pathname.includes("/setup");
      return redirected || !loading;
    },
    { timeout: timeoutMs }
  );
  return nowMs() - t0;
}

async function waitRouteReady(page, route, timeoutMs) {
  const t0 = nowMs();
  const checks = {
    "/app/": () => {
      const t = document.body?.innerText || "";
      return (
        t.includes("Schedules") ||
        t.includes("Zeitpläne") ||
        t.includes("Home") ||
        t.includes("Start")
      );
    },
    "/app/dashboard": () => {
      const t = document.body?.innerText || "";
      return (
        t.includes("Actions") ||
        t.includes("Aktionen") ||
        t.includes("Workspace") ||
        t.includes("Arbeitsbereich") ||
        t.includes("Hub")
      );
    },
    "/app/chat": () => {
      const t = document.body?.innerText || "";
      return t.includes("Chat") && !t.match(/^Agent Layer[\s\S]*Wird geladen[\s\S]*$/);
    },
  };
  const fn = checks[route] || (() => {
    const t = document.body?.innerText || "";
    return t.trim().length > 80;
  });
  await page.waitForFunction(fn, { timeout: timeoutMs });
  return nowMs() - t0;
}

async function collectResourceTimings(page, baseUrl) {
  try {
    return await page.evaluate((origin) => {
      return performance
        .getEntriesByType("resource")
        .filter(
          (r) =>
            r.name.includes("/v1/") ||
            r.name.includes("/auth/") ||
            r.name.includes("/ws/")
        )
        .map((r) => ({
          url: r.name.replace(origin, ""),
          ms: Math.round(r.duration),
        }))
        .sort((a, b) => b.ms - a.ms)
        .slice(0, 12);
    }, baseUrl);
  } catch {
    return [];
  }
}

async function measureUnauthProtected(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const network = attachNetwork(page);
  const t0 = nowMs();
  await page.goto(`${base}/app/dashboard`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  const domMs = nowMs() - t0;
  let spinnerMs = 0;
  let finalUrl = page.url();
  try {
    spinnerMs = await waitUntilNotAuthLoading(page, 20_000);
    finalUrl = page.url();
  } catch {
    spinnerMs = nowMs() - t0;
  }
  const api = summarizeApiCalls(network);
  await context.close();
  return {
    route: "/app/dashboard (no session)",
    dom_ms: domMs,
    spinner_until_redirect_ms: spinnerMs,
    final_url: finalUrl.replace(base, ""),
    api_calls: api,
  };
}

async function login(page, email, password) {
  const t0 = nowMs();
  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 });
  return nowMs() - t0;
}

async function measureAuthRoute(browser, route, email, password) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const network = attachNetwork(page);
  const loginMs = await login(page, email, password);
  const tNav = nowMs();
  await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  const domMs = nowMs() - tNav;
  let readyMs = 0;
  try {
    readyMs = await waitRouteReady(page, route, 30_000);
  } catch {
    readyMs = nowMs() - tNav;
  }
  const resources = await collectResourceTimings(page, base);
  const api = summarizeApiCalls(network);
  for (const r of resources) {
    const existing = api.find((a) => a.path === r.url.split("?")[0]);
    if (!existing) {
      api.push({
        path: r.url.split("?")[0],
        method: "GET",
        ms: r.ms,
        status: null,
      });
    } else if (r.ms > existing.ms) {
      existing.ms = r.ms;
    }
  }
  api.sort((a, b) => b.ms - a.ms);
  await context.close();
  return {
    route,
    login_ms: loginMs,
    dom_ms: domMs,
    ready_ms: readyMs,
    total_ms: loginMs + domMs + readyMs,
    slow_resources: resources.filter((r) => r.ms > 100),
    api_calls: api,
  };
}

async function measureConcurrentDashboards(browser, email, password, n = 2) {
  const workers = [];
  for (let i = 0; i < n; i += 1) {
    workers.push(
      (async () => {
        const context = await browser.newContext();
        const page = await context.newPage();
        await login(page, email, password);
        const t0 = nowMs();
        await page.goto(`${base}/app/dashboard`, {
          waitUntil: "domcontentloaded",
          timeout: 45_000,
        });
        await waitRouteReady(page, "/app/dashboard", 30_000);
        const ms = nowMs() - t0;
        await context.close();
        return ms;
      })()
    );
  }
  const latencies = await Promise.all(workers);
  latencies.sort((a, b) => a - b);
  return {
    n,
    latencies_ms: latencies,
    max_ms: Math.max(...latencies),
    min_ms: Math.min(...latencies),
  };
}

async function main() {
  loadDotenv(join(REPO, ".env"));
  loadDotenv(join(REPO, ".env.e2e"));

  const headless = process.env.E2E_HEADED !== "1";
  let browser;
  try {
    browser = await chromium.launch({ headless });
  } catch (e) {
    console.error("[runtime-e2e] Playwright chromium missing:", String(e));
    process.exit(2);
  }

  const report = {
    base,
    scenarios: [],
    concurrent: null,
    errors: [],
  };

  try {
    report.scenarios.push(await measureUnauthProtected(browser));
    const c = creds();
    if (c) {
      for (const route of ["/app/", "/app/dashboard", "/app/chat"]) {
        report.scenarios.push(
          await measureAuthRoute(browser, route, c.email, c.password)
        );
      }
      report.concurrent = await measureConcurrentDashboards(
        browser,
        c.email,
        c.password,
        2
      );
    } else {
      report.errors.push(
        "authenticated routes skipped — set AGENT_INITIAL_ADMIN_EMAIL/PASSWORD in .env"
      );
    }
  } catch (err) {
    report.errors.push(String(err).slice(0, 300));
  } finally {
    await browser.close();
  }

  console.log(`__RUNTIME_E2E_JSON__${JSON.stringify(report)}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
