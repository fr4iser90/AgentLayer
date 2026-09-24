#!/usr/bin/env node
/**
 * Ink-colour guard (ratchet).
 *
 * Welle 1 moved the grey/white text scale onto `ink-*`: raw text-white /
 * text-neutral-* went from ~1280 occurrences to 131, and rendered on-token text
 * area from 43.0 % to 85.2 %. What remains is foreign semantics — text-amber-*,
 * text-sky-*, text-emerald-* and friends — which carry meaning and need a
 * per-case mapping decision, not a mechanical sweep.
 *
 * So this is a ratchet, not a clean-room check: the current violations are
 * recorded in scripts/ink-baseline.json and are tolerated. Any text colour that
 * is neither a design token nor already in the baseline fails. Drift is caught
 * immediately; the existing debt is tracked rather than hidden.
 *
 * Allow-list rather than deny-list, for the reason documented in
 * check-field-surface.mjs: a deny-list of `white|neutral|gray|zinc` waves the
 * next `text-slate-300` straight through.
 *
 * Run with --update to re-record the baseline after an intentional migration.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "ink-baseline.json");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// Design tokens that may paint text.
const TOKEN = new Set([
  "ink",
  "ink-primary",
  "ink-secondary",
  "ink-muted",
  "ink-faint",
  "ink-on-fill",
  "accent",
  "accent-hover",
  "accent-press",
  "success",
  "success-hover",
  "warning",
  "warning-hover",
  "danger",
  "danger-hover",
  "badge-accent",
  "badge-success",
  "badge-warning",
  "badge-danger",
  "transparent",
  "inherit",
  "current",
]);

// The trailing boundary must accept the quote that closes a className attribute,
// not just whitespace. `(?=\s|$)` alone never matches the LAST class in every
// class string — a planted `text-slate-300` walked straight through a guard
// that then reported OK.
//
// The value class must also admit `/`, for the opacity modifier. Without it
// `text-sky-400/90` fails the lookahead at the slash and is invisible: the
// guard saw 314 raw text colours while 563 were in the tree, and a newly added
// `text-red-500/50` would have passed. `check-border-token.mjs` already
// carries `/` in its class for exactly this reason — the lesson was learned
// there and never propagated here.
//
// The variant-prefix chain must be admitted too. Anchoring on whitespace alone
// left `hover:text-sky-300`, `focus:text-amber-300/90` and `sm:hover:text-red-200`
// unseen — 80 prefixed raw text colours in the tree, and a newly added
// `hover:text-red-500` would have passed. This is the third shape of the same
// defect in this file's lifetime: value class, then opacity, then prefix.
//
// The prefix is captured but NOT part of the reported key. `hover:text-sky-300`
// and `text-sky-300` are the same colour decision in the same file, and this
// guard tracks which raw colours appear where — keying by variant would count
// one decision twice without adding information.
const TEXT_CLASS =
  /(^|\s|["'`])((?:[a-zA-Z0-9-]+:)*text-)([a-z0-9][a-z0-9/-]*)(?=[\s"'`]|$)/g;
const GREYSCALE = /^(white|black|neutral-\d+|gray-\d+|zinc-\d+|slate-\d+)$/;
const FOREIGN =
  /^(red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d+$/;

/**
 * End of a JSX tag, scanning past `>` inside expressions.
 * Copied from check-field-surface.mjs: a plain `<x\b[^>]*?>` stops at the `>`
 * of `onChange={(e) => …}` and never inspects the className that follows.
 */
function tagEnd(src, open) {
  let depth = 0;
  let quote = null;
  for (let i = open + 1; i < src.length; i += 1) {
    const c = src[i];
    if (quote) {
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") quote = c;
    else if (c === "{") depth += 1;
    else if (c === "}") depth -= 1;
    else if (c === ">" && depth === 0) return i + 1;
  }
  return -1;
}

function classify(token) {
  const bare = token.split("/")[0];
  if (TOKEN.has(bare)) return null;
  if (GREYSCALE.test(bare)) return "greyscale";
  if (FOREIGN.test(bare)) return "foreign";
  return null;
}

/**
 * Pure scan of one source string. Exported so the matcher itself is testable:
 * every blind spot here is a silent undercount, and the only way to catch "the
 * guard stopped seeing the thing it guards" is to assert the population, not
 * just the verdict. Until now this file exported only `checkInkColor()`, which
 * needs a filesystem — so none of the three defects above could be pinned.
 */
export function scanTextTokens(src) {
  const tokens = [];
  TEXT_CLASS.lastIndex = 0;
  let m;
  while ((m = TEXT_CLASS.exec(src)) !== null) tokens.push(m[3]);
  return tokens;
}

export { classify };

export async function checkInkColor() {
  let baseline = {};
  try {
    baseline = JSON.parse(await readFile(BASELINE, "utf8"));
  } catch {
    baseline = {};
  }

  const findings = [];
  const current = {};

  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file);
    const text = await readFile(file, "utf8");
    const here = new Set();
    const fresh = [];
    const TAG_START = /<[a-zA-Z][a-zA-Z0-9.]*/g;
    let m;
    while ((m = TAG_START.exec(text)) !== null) {
      const end = tagEnd(text, m.index);
      if (end === -1) continue;
      const tag = text.slice(m.index, end);
      const line = text.slice(0, m.index).split("\n").length;
      TEXT_CLASS.lastIndex = 0;
      let t;
      while ((t = TEXT_CLASS.exec(tag)) !== null) {
        const token = t[3];
        const kind = classify(token);
        if (!kind) continue;
        const key = `text-${token}`;
        here.add(key);
        const allowed = new Set(baseline[rel] || []);
        if (!allowed.has(key)) {
          fresh.push({ line, cls: key, kind });
        }
      }
      TAG_START.lastIndex = end;
    }
    if (here.size) current[rel] = [...here].sort();
    if (fresh.length) findings.push({ file: rel, issues: fresh });
  }

  return { ok: findings.length === 0, findings, current };
}

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((e) => p.endsWith(e)) && !SKIP.some((re) => re.test(p))) yield p;
  }
}

async function main() {
  const { ok, findings, current } = await checkInkColor();

  if (process.argv.includes("--update")) {
    await writeFile(BASELINE, JSON.stringify(current, null, 2) + "\n", "utf8");
    const n = Object.values(current).reduce((a, v) => a + v.length, 0);
    console.log(`[ink-color] baseline re-recorded: ${n} tolerated class(es) in ${Object.keys(current).length} file(s).`);
    return;
  }

  if (!ok) {
    const total = findings.reduce((n, f) => n + f.issues.length, 0);
    console.error(
      `[ink-color] ${total} new raw text colour(s) in ${findings.length} file(s) — not a token, not in the baseline.`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) {
        console.error(`    L${i.line} ${i.cls}  (${i.kind})`);
      }
      if (issues.length > 8) console.error(`    … +${issues.length - 8} more`);
    }
    console.error("\n[ink-color] Use text-ink-primary / secondary / muted / faint / on-fill.");
    console.error("[ink-color] For semantic colour use accent|success|warning|danger or badge-*.");
    console.error("[ink-color] If this is an intentional migration, re-record: node scripts/check-ink-color.mjs --update");
    process.exit(1);
  }
  console.log("[ink-color] OK — no new raw text colours beyond the recorded baseline.");
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
