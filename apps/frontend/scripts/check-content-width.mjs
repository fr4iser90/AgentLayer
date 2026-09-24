#!/usr/bin/env node
/**
 * Content-width guard (ratchet).
 *
 * Every `max-w-*` must name a token from tailwind.config.js's maxWidth block.
 * Tailwind's own scale (`max-w-md`, `max-w-4xl`) and arbitrary values
 * (`max-w-[13rem]`) are violations: they are sizes without a purpose, which is
 * how nine settings pages at one nav level ended up with four different page
 * widths.
 *
 * The allowed names are read from the config at runtime via width-scan.mjs, not
 * duplicated here. A guard that keeps its own copy of the ramp goes quiet when
 * the config renames a token; this one turns that rename into a violation.
 *
 * Ratchet rather than hard because the migration is in progress. The tolerated
 * set lives in scripts/width-baseline.json. New off-token widths fail
 * immediately; existing debt is tracked rather than hidden. When the baseline
 * reaches zero, flip HARD to true and it becomes a clean-room check like the
 * radius guard.
 *
 * Run with --update to re-record the baseline after an intentional migration.
 * Run with --explain to print the value distribution without failing.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { widthTokens, isToken, TOKENS } from "./width-scan.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "width-baseline.json");

// Flip to true once the baseline is empty, making this a clean-room check.
const HARD = false;

const SCAN_EXT = [".tsx", ".jsx", ".ts", ".js"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !re_skip(p)) yield p;
  }
}

function re_skip(p) {
  return SKIP.some((r) => r.test(p));
}

/**
 * Pure scan of one source string. Exported so the guard's own recognition can
 * be tested: every bug in the matcher is a silent undercount, and the only way
 * to catch "the guard stopped seeing the thing it guards" is to assert the
 * population, not just the verdict.
 */
export function scanWidths(src) {
  const values = [];
  let onToken = 0;
  for (const [tok, value] of widthTokens(src)) {
    const hit = isToken(value);
    if (hit) onToken += 1;
    values.push({ token: tok, value, onToken: hit });
  }
  return { total: values.length, onToken, offToken: values.length - onToken, values };
}

export async function checkContentWidth() {
  let baseline = {};
  try {
    baseline = JSON.parse(await readFile(BASELINE, "utf8"));
  } catch {
    baseline = {};
  }

  const findings = [];
  const current = {};
  const distribution = new Map();
  let tokens = 0;
  let total = 0;

  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file);
    const text = await readFile(file, "utf8");
    const here = new Set();
    const fresh = [];
    const lines = text.split("\n");

    // Line-level scan for reporting; token discovery uses the shared scanner so
    // nested template strings are covered the same way the codemod covers them.
    for (const [tok, value] of widthTokens(text)) {
      total += 1;
      distribution.set(value, (distribution.get(value) ?? 0) + 1);
      if (isToken(value)) {
        tokens += 1;
        continue;
      }
      here.add(value);
      const allowed = new Set(baseline[rel] ?? []);
      if (!allowed.has(value)) {
        const line = lines.findIndex((l) => l.includes(tok)) + 1;
        fresh.push({ line, cls: tok, value });
      }
    }
    if (here.size) current[rel] = [...here].sort();
    if (fresh.length) findings.push({ file: rel, issues: fresh });
  }

  return { ok: findings.length === 0, findings, current, distribution, tokens, total };
}

async function main() {
  const { ok, findings, current, distribution, tokens, total } = await checkContentWidth();

  if (process.argv.includes("--update")) {
    await writeFile(BASELINE, JSON.stringify(current, null, 2) + "\n", "utf8");
    const n = Object.values(current).reduce((a, v) => a + v.length, 0);
    console.log(
      `[width] baseline re-recorded: ${n} tolerated value(s) in ${Object.keys(current).length} file(s).`
    );
    return;
  }

  if (process.argv.includes("--explain")) {
    console.log(`[width] ${TOKENS.size} Token definiert, ${total} max-w-* Stellen`);
    console.log(`[width] auf Token: ${tokens} · off-Token: ${total - tokens}`);
    const rows = [...distribution.entries()].sort((a, b) => b[1] - a[1]);
    console.log("[width] Verteilung:");
    for (const [v, n] of rows) {
      console.log(`  ${String(n).padStart(3)}  max-w-${v}  ${isToken(v) ? "[TOKEN]" : ""}`);
    }
    return;
  }

  if (!ok) {
    const totalNew = findings.reduce((n, f) => n + f.issues.length, 0);
    console.error(
      `[width] ${totalNew} neue off-Token Breite(n) in ${findings.length} Datei(en) — kein maxWidth-Token, nicht in der Baseline.`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) {
        console.error(`    L${i.line} max-w-${i.value}`);
      }
      if (issues.length > 8) console.error(`    … +${issues.length - 8} mehr`);
    }
    console.error("\n[width] Erlaubte Token: " + [...TOKENS].join(", "));
    console.error("[width] Bewusste Migration? node scripts/check-content-width.mjs --update");
    process.exit(HARD ? 1 : 1);
  }
  console.log(
    `[width] OK - ${total} max-w-* Stellen geprüft, ${tokens} auf Token, keine neue Drift über die aufgezeichnete Baseline.`
  );
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
