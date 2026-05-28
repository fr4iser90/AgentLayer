#!/usr/bin/env node
/**
 * Browser E2E: login (.env), visit each app route, verify DE/EN markers + no fatal JS errors.
 * Run: npm run e2e:i18n  (or scripts/run-e2e-playwright-i18n.sh via Docker)
 */
import { chromium } from "playwright";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { APP_ROUTES } from "./routes-manifest.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(__dirname, "..");
const REPO = join(FRONTEND, "../..");

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
    console.error(
      "[e2e] Missing AGENT_INITIAL_ADMIN_EMAIL/PASSWORD (or AGENT_E2E_*) in .env"
    );
    process.exit(1);
  }
  return { email, password };
}

const base = (process.env.AGENT_E2E_BASE_URL || "http://127.0.0.1:8088").replace(
  /\/$/,
  ""
);

/** At least one marker must appear in visible body text for the locale. */
const ROUTE_MARKERS = {
  "/app/login": {
    de: ["Anmelden", "Melden Sie sich"],
    en: ["Sign in", "Sign in with"],
  },
  "/app/setup": {
    de: ["Ersteinrichtung", "Einrichtung", "Schritt"],
    en: ["initial setup", "Step", "administrator"],
  },
  "/app/": {
    de: ["Start", "Arbeitsbereich", "Zeitpläne"],
    en: ["Home", "Dashboard", "Schedules"],
  },
  "/app/chat": { de: ["Chat"], en: ["Chat"] },
  "/app/studio": { de: ["Bildgenerierung", "Studio"], en: ["Studio", "image"] },
  "/app/dashboard": {
    de: ["Arbeitsbereich", "Dashboard"],
    en: ["Dashboard", "Workspace"],
  },
  "/app/schedules": { de: ["Zeitpläne", "Zeitplan"], en: ["Schedules", "Schedule"] },
  "/app/tasks": { de: ["Aufgaben", "Aufgabe"], en: ["Tasks", "Task"] },
  "/app/docs": { de: ["Dokumentation", "Docs"], en: ["Documentation", "Docs"] },
  "/app/settings/profile": {
    de: ["Anzeigename", "Zeitzone", "Profil"],
    en: ["Display name", "Timezone", "Profile"],
  },
  "/app/settings/friends": {
    de: ["Freunde", "Friends"],
    en: ["Friends", "friend"],
  },
  "/app/settings/connections": {
    de: ["Connections", "Verbindung", "Discord"],
    en: ["Connections", "Discord"],
  },
  "/app/settings/tools": {
    de: ["Tools", "Werkzeug", "Secrets"],
    en: ["Tools", "Secrets"],
  },
  "/app/settings/agent": {
    de: ["Agent", "Persona", "Persona"],
    en: ["Agent", "Persona"],
  },
  "/app/settings/shares": { de: ["Shares", "Freigabe"], en: ["Shares", "share"] },
  "/app/admin": {
    de: ["Administration", "Admin", "Operator"],
    en: ["Admin", "Operator"],
  },
  "/app/admin/interfaces": {
    de: ["Schnittstellen", "Interfaces", "Übersicht"],
    en: ["Interfaces", "Overview"],
  },
  "/app/admin/interfaces/bridges": {
    de: ["Bridges", "Discord", "Telegram"],
    en: ["Bridges", "Discord"],
  },
  "/app/admin/interfaces/llm": { de: ["LLM", "Modell"], en: ["LLM", "model"] },
  "/app/admin/interfaces/memory": { de: ["Memory", "Speicher", "Embedding"], en: ["Memory", "Embedding"] },
  "/app/admin/interfaces/automation": {
    de: ["Automation", "Scheduler", "Zeitplan"],
    en: ["Automation", "Scheduler"],
  },
  "/app/admin/interfaces/platform": {
    de: ["Platform", "Plattform"],
    en: ["Platform"],
  },
  "/app/admin/tools": { de: ["Tools", "Paket"], en: ["Tools", "package"] },
  "/app/admin/users": { de: ["Benutzer", "Users", "Tenant"], en: ["Users", "Tenant"] },
  "/app/admin/scheduled-jobs": {
    de: ["Jobs", "geplant", "Scheduled"],
    en: ["Scheduled", "Jobs"],
  },
  "/app/admin/schedules": { de: ["Zeitpläne", "Schedules"], en: ["Schedules"] },
  "/app/admin/run-traces": {
    de: ["Traces", "Trace", "Lauf"],
    en: ["Traces", "Trace", "run"],
  },
};

const DEFAULT_MARKERS = {
  de: ["Einstellungen", "Abmelden", "Agent Layer"],
  en: ["Settings", "Sign out", "Agent Layer"],
};

function markersFor(path) {
  return ROUTE_MARKERS[path] || DEFAULT_MARKERS;
}

function fatalJs(msg) {
  return (
    /is not a function/i.test(msg) ||
    /is not defined/i.test(msg) ||
    /ReferenceError/i.test(msg) ||
    /TypeError/i.test(msg)
  );
}

async function setLanguage(context, lang) {
  await context.addInitScript((lng) => {
    localStorage.setItem("agent-ui.lang", lng);
  }, lang);
}

async function bodyText(page) {
  return page.locator("body").innerText({ timeout: 15_000 });
}

function hasMarker(text, list) {
  const lower = text.toLowerCase();
  return list.some((m) => lower.includes(m.toLowerCase()));
}

async function login(page, email, password) {
  await page.goto(`${base}/app/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), {
    timeout: 30_000,
  });
}

async function checkRoute(browser, route, lang, needsAuth, email, password) {
  const context = await browser.newContext();
  await setLanguage(context, lang);
  const page = await context.newPage();
  const jsErrors = [];
  page.on("pageerror", (err) => {
    if (fatalJs(String(err))) jsErrors.push(String(err).slice(0, 200));
  });

  if (needsAuth) {
    await login(page, email, password);
    await setLanguage(context, lang);
    await page.goto(`${base}${route}`, { waitUntil: "networkidle", timeout: 45_000 });
  } else {
    await page.goto(`${base}${route}`, { waitUntil: "networkidle", timeout: 45_000 });
  }

  await page.waitForTimeout(800);
  const text = await bodyText(page);
  const mk = markersFor(route)[lang];
  const i18nOk = hasMarker(text, mk);
  await context.close();

  const issues = [];
  if (!i18nOk) issues.push(`no ${lang} marker (${mk.slice(0, 3).join("|")}…)`);
  if (jsErrors.length) issues.push(`JS: ${jsErrors[0]}`);
  return issues;
}

async function main() {
  loadDotenv(join(REPO, ".env"));
  loadDotenv(join(REPO, ".env.e2e"));
  const { email, password } = creds();

  const headless = process.env.E2E_HEADED !== "1";
  let browser;
  try {
    browser = await chromium.launch({ headless });
  } catch (e) {
    console.error("[e2e] Playwright chromium missing. Run: npx playwright install chromium");
    console.error(String(e));
    process.exit(1);
  }

  const results = [];
  const publicRoutes = new Set(["/app/login", "/app/setup"]);

  console.log(`[e2e] base=${base} routes=${APP_ROUTES.length} headless=${headless}`);

  try {
    for (const { path: routePath, auth } of APP_ROUTES) {
      const needsAuth = auth !== "public";
      for (const lang of ["de", "en"]) {
        let issues = await checkRoute(
          browser,
          routePath,
          lang,
          needsAuth,
          email,
          password
        );
        if (
          routePath === "/app/setup" &&
          issues.some((x) => x.startsWith("no "))
        ) {
          const ctx = await browser.newContext();
          await setLanguage(ctx, lang);
          const page = await ctx.newPage();
          await login(page, email, password);
          await page.goto(`${base}${routePath}`, {
            waitUntil: "networkidle",
            timeout: 45_000,
          });
          const url = page.url();
          await ctx.close();
          if (!url.includes("/setup")) {
            issues = issues.filter((x) => !x.startsWith("no "));
            if (!issues.length) {
              console.log(
                `[e2e] OK ${lang} ${routePath} (skipped markers — instance already set up, redirected)`
              );
              results.push({ route: routePath, lang, status: "OK", issues: [] });
              continue;
            }
          }
        }
        const status = issues.length ? "FAIL" : "OK";
        results.push({ route: routePath, lang, status, issues });
        console.log(
          `[e2e] ${status} ${lang} ${routePath}${issues.length ? " — " + issues.join("; ") : ""}`
        );
      }
    }
  } finally {
    await browser.close();
  }

  const failed = results.filter((r) => r.status === "FAIL");
  if (failed.length) {
    console.error(`\n[e2e] ${failed.length}/${results.length} checks failed`);
    process.exit(1);
  }
  console.log(`\n[e2e] All ${results.length} route×locale checks passed`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
