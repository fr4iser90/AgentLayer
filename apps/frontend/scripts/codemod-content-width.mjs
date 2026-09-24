#!/usr/bin/env node
/**
 * Content-width codemod.
 *
 * Applies scripts/width-migration.mjs. Each entry rewrites one class token on
 * one line, preserving any responsive/state prefix: `sm:max-w-lg` becomes
 * `sm:max-w-drawer`, not `sm:max-w-drawer` with the prefix lost.
 *
 * Entries are applied bottom-up within a file so that rewriting a later line
 * never invalidates the line numbers of earlier entries.
 *
 * --dry-run prints what would change without writing.
 */
import { readFile, writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { MIGRATION } from "./width-migration.mjs";
import { TOKENS } from "./width-scan.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const DRY = process.argv.includes("--dry-run");

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Replace one width token on one line, keeping its prefix chain.
 * Returns the new line, or null when the token is not present.
 */
function replaceOnLine(line, from, to) {
  // Prefix chain, then `max-w-`, then the exact value bounded so `md` cannot
  // hit `mdx`, and a bracketed value must close.
  const re = new RegExp(`((?:[a-zA-Z0-9-]+:)*max-w-)${escapeRe(from)}(?![a-z0-9-])`, "g");
  if (!re.test(line)) return null;
  re.lastIndex = 0;
  if (to === null) {
    return line
      .replace(re, "")
      .replace(/[ \t]{2,}/g, " ")
      .replace(/(["'`])\s+/g, "$1")
      .replace(/\s+(["'`])/g, " $1");
  }
  return line.replace(re, `$1${to}`);
}

let filesChanged = 0;
let totalApplied = 0;
const misses = [];

for (const [rel, entries] of Object.entries(MIGRATION)) {
  const path = join(ROOT, rel);
  const src = await readFile(path, "utf8");
  const lines = src.split("\n");

  for (const t of entries) {
    if (t.to !== null && !TOKENS.has(t.to)) {
      throw new Error(`${rel}:${t.line} -> max-w-${t.to} is not a config token`);
    }
  }

  const ordered = [...entries].sort((a, b) => b.line - a.line);
  let applied = 0;
  for (const e of ordered) {
    const idx = e.line - 1;
    if (idx < 0 || idx >= lines.length) {
      misses.push(`${rel}:${e.line} — line out of range`);
      continue;
    }
    const next = replaceOnLine(lines[idx], e.from, e.to);
    if (next === null) {
      misses.push(`${rel}:${e.line} — max-w-${e.from} not found on that line`);
      continue;
    }
    lines[idx] = next;
    applied += 1;
  }

  if (applied > 0) {
    filesChanged += 1;
    totalApplied += applied;
    if (!DRY) await writeFile(path, lines.join("\n"), "utf8");
  }
}

console.log(
  `${DRY ? "[dry-run] " : ""}[width-codemod] ${totalApplied} Stelle(n) in ${filesChanged} Datei(en) umgestellt.`
);
if (misses.length) {
  console.log(`[width-codemod] ${misses.length} Eintrag(e) nicht angewandt:`);
  for (const m of misses) console.log(`  ${m}`);
}
