#!/usr/bin/env node
/**
 * Static checks: hardcoded user-facing strings, forbidden t-shadowing, page i18n usage.
 */
import { readFile, readdir, stat } from "node:fs/promises";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { APP_ROUTES } from "./routes-manifest.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_DIRS = ["pages", "features", "layout", "auth"];

/** Lines matching these are allowed (technical / API identifiers). */
const LINE_ALLOW = [
  /Content-Type/,
  /application\/json/,
  /font-mono/,
  /<code/,
  /option value="/,
  /import /,
  /from "/,
  /console\./,
  /\/v1\//,
  /GET \/|POST \/|PATCH \//,
  /EMBEDDING_|TOOL_|AGENT_|\.env/,
  /scheduler_jobs/,
  /google_calendar|calendar_ics/,
  /tenants\.id/,
  /ollama|external/,
  /value="user"|value="admin"/,
  /Implement the agreed plan/,
  /wsUrl\(/,
  /throw new Error\(/,
  /DOMException/,
  /AbortError/,
  /role === |\.role ===/,
  /access_role/,
  /HTTP \$\{/,
  /\(empty\)/,
  /→ |round |chars| ms\)| min\)/,
  /agent\./,
  /JSON\.stringify/,
];

const FILE_ALLOW_PATTERNS = [
  /\.d\.ts$/,
  /i18n\/config\.ts$/,
  /modelCatalog\.ts$/,
  /api\.ts$/,
  /chatThreadStorage\.ts$/,
  /messageFormat\.ts$/,
  /schedulerExecutionTarget\.ts$/,
  /toolPrefs\.ts$/,
  /dashboardDataPaths\.ts$/,
  /dashboardHubNav\.ts$/,
  /workspaceMcpBuilders\.ts$/,
  /confirmWorkspaceScope\.ts$/,
  /openaiSseStream\.ts$/,
];

async function walk(dir, out = []) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === "locales" || e.name === "node_modules") continue;
      await walk(p, out);
    } else if (/\.(tsx|ts)$/.test(e.name)) {
      out.push(p);
    }
  }
  return out;
}

function allowedFile(rel) {
  return FILE_ALLOW_PATTERNS.some((re) => re.test(rel));
}

function allowedLine(line) {
  const t = line.trim();
  if (!t || t.startsWith("//") || t.startsWith("*") || t.startsWith("/*")) return true;
  return LINE_ALLOW.some((re) => re.test(line));
}

function checkHardcoded(content, rel) {
  const issues = [];
  const lines = content.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (allowedLine(line)) continue;

    if (/placeholder="[^{]/.test(line)) {
      issues.push({ line: i + 1, rule: "placeholder", snippet: line.trim().slice(0, 120) });
    }
    if (/aria-label="[^{]/.test(line)) {
      issues.push({ line: i + 1, rule: "aria-label", snippet: line.trim().slice(0, 120) });
    }
    if (/\btitle="[^{]/.test(line) && !/title=\{/.test(line)) {
      issues.push({ line: i + 1, rule: "title-attr", snippet: line.trim().slice(0, 120) });
    }
    if (/set(Error|Msg|Err)\(\s*"/.test(line)) {
      issues.push({ line: i + 1, rule: "setError-msg-literal", snippet: line.trim().slice(0, 120) });
    }
    if (/window\.confirm\(\s*"/.test(line) || /[^a-zA-Z]confirm\(\s*"/.test(line)) {
      if (!/confirm\(\s*t\(/.test(line)) {
        issues.push({ line: i + 1, rule: "confirm-literal", snippet: line.trim().slice(0, 120) });
      }
    }
    if (/window\.prompt\(\s*"/.test(line) || /prompt\(\s*"/.test(line)) {
      if (!/prompt\(\s*t\(/.test(line)) {
        issues.push({ line: i + 1, rule: "prompt-literal", snippet: line.trim().slice(0, 120) });
      }
    }
    if (/[äöüÄÖÜß]/.test(line)) {
      issues.push({ line: i + 1, rule: "german-umlaut", snippet: line.trim().slice(0, 120) });
    }

    if (/>=|<=| as Record|mapListItemToThread|Promise<|ReturnType</.test(line)) continue;
    if (/\.map\(\(t\)\s*=>/.test(line) && /title=\{t\(|t\("chat:/.test(line)) {
      issues.push({ line: i + 1, rule: "t-shadowing-jsx", snippet: line.trim().slice(0, 100) });
    }
    if (!/<\/?[a-z][a-z0-9]*[\s>/]/.test(line)) continue;
    const jsxText = line.match(/>([^<{]+)</);
    if (jsxText) {
      const text = jsxText[1].trim();
      if (
        text.length >= 8 &&
        /[A-Za-z]{3,}/.test(text) &&
        /\s/.test(text) &&
        !/^[\d\s▲▼✕…•·|,.:;!?+\-/\\()[\]]+$/.test(text)
      ) {
        issues.push({ line: i + 1, rule: "jsx-text", snippet: text.slice(0, 80) });
      }
    }
  }

  return issues;
}

function checkTShadowing(content, rel) {
  const issues = [];
  const bad = [
    /const t = threads\.find/,
    /const t = await createConversation/,
    /const t = mdata\./,
    /const t = formatMessageTime/,
    /async \(t: ChatThread\)\s*=>/,
    /setSelectedAgentId/,
    /if \(!t \|\| !routed\)/,
  ];
  for (const re of bad) {
    if (re.test(content)) {
      issues.push({ rule: "t-shadowing", pattern: re.source });
    }
  }
  return issues;
}

function checkPageUsesI18n(content) {
  return /useTranslation\(/.test(content) || /i18n\.t\(/.test(content);
}

async function scanUiFiles() {
  const files = [];
  for (const d of SCAN_DIRS) {
    const dir = join(SRC, d);
    await walk(dir, files);
  }
  let ok = true;
  const report = { hardcoded: [], shadowing: [], missingI18n: [] };

  for (const abs of files) {
    const rel = relative(ROOT, abs);
    if (allowedFile(rel)) continue;
    const content = await readFile(abs, "utf8");
    const hard = checkHardcoded(content, rel);
    const shadow = checkTShadowing(content, rel);
    if (hard.length) {
      report.hardcoded.push({ file: rel, issues: hard });
      ok = false;
    }
    if (shadow.length) {
      report.shadowing.push({ file: rel, issues: shadow });
      ok = false;
    }
    if (rel.startsWith("pages/") && !checkPageUsesI18n(content)) {
      report.missingI18n.push(rel);
      ok = false;
    }
  }
  return { ok, report };
}

async function scanRoutes() {
  let ok = true;
  const missing = [];
  const noI18n = [];
  for (const route of APP_ROUTES) {
    const abs = join(ROOT, "src", route.file);
    try {
      await stat(abs);
    } catch {
      missing.push(route);
      ok = false;
      continue;
    }
    const content = await readFile(abs, "utf8");
    if (!checkPageUsesI18n(content)) {
      noI18n.push(route.path);
      ok = false;
    }
  }
  return { ok, missing, noI18n };
}

export async function runScanI18nUi() {
  const ui = await scanUiFiles();
  const routes = await scanRoutes();
  const ok = ui.ok && routes.ok;
  return { ok, ui, routes };
}

async function main() {
  const { ok, ui, routes } = await runScanI18nUi();
  if (ui.report.hardcoded.length) {
    console.error("[i18n-ui] Hardcoded UI strings:");
    for (const { file, issues } of ui.report.hardcoded) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) {
        console.error(`    L${i.line} [${i.rule}] ${i.snippet}`);
      }
      if (issues.length > 8) console.error(`    … +${issues.length - 8} more`);
    }
  }
  if (ui.report.shadowing.length) {
    console.error("[i18n-ui] t() shadowing risks:");
    for (const { file, issues } of ui.report.shadowing) {
      console.error(`  ${file}:`, issues.map((i) => i.pattern).join(", "));
    }
  }
  if (ui.report.missingI18n.length) {
    console.error("[i18n-ui] Pages without useTranslation:", ui.report.missingI18n.join(", "));
  }
  if (routes.missing.length) {
    console.error("[i18n-ui] Route files missing:", routes.missing.map((r) => r.file).join(", "));
  }
  if (routes.noI18n.length) {
    console.error("[i18n-ui] Routes without i18n:", routes.noI18n.join(", "));
  }
  if (!ok) process.exit(1);
  console.log(
    `[i18n-ui] OK — ${APP_ROUTES.length} routes, scanned pages/features/layout/auth for hardcoded UI & t-shadowing.`
  );
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
