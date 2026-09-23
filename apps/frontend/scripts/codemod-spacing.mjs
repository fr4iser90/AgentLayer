#!/usr/bin/env node
/**
 * Spacing codemod — numeric Tailwind steps onto the named density ramp.
 *
 * The ramp is defined in tailwind.config.js and was measured from the app's
 * 5248 spacing classes, not invented.
 *
 *   0.5 (2px)  -> hair      4    (16px) -> wide
 *   1   (4px)  -> tight     5    (20px) -> roomy
 *   1.5 (6px)  -> snug      6    (24px) -> broad
 *   2   (8px)  -> base      8    (32px) -> deep
 *   2.5 (10px) -> firm      10   (40px) -> page
 *   3   (12px) -> soft      12   (48px) -> grand
 *
 * Every mapping is pixel-exact. Nothing in this codemod moves a rendered
 * pixel — it only renames. That is deliberate: 2.5 and 10 and 12 each got
 * their own ramp step rather than being folded onto a neighbour, because
 * 2.5 alone is 62 call sites including the Button primitive's `sm` size,
 * where folding onto 12px would have made `sm` and `md` horizontally
 * identical.
 *
 * Left alone on purpose:
 *
 *   0     `p-0` / `m-0` read as "explicitly zero", a statement rather
 *         than a ramp position.
 *   px    Tailwind's built-in 1px. Three uses, all hairline icon-button
 *         insets, where 2px would be wrong.
 *   7, 14, 16, 20, 24   28/56/64/80/96px, eight one-off call sites.
 *         Naming a token per singleton makes the ramp worse than tolerating
 *         the debt; check-spacing.mjs baselines them instead.
 *
 * Semantic names rather than numeric ones on purpose: Tailwind's own scale is
 * already 4px-based, so a numeric rename would be a no-op that could not be
 * told apart from off-ramp drift. Named steps are what let the guard reject
 * `p-7` while accepting `p-soft`.
 *
 * Run with --dry to see the plan without writing.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { UTIL, rewriteSpacing } from "./spacing-scan.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const SCAN_EXT = [".tsx", ".jsx", ".ts", ".js"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// Tailwind numeric step -> named ramp step. Read with .get only, never with
// bracket notation (prototype chain: `constructor` reads truthy, real keys
// read undefined — see the border codemod).
const MAP = new Map([
  ["0.5", "hair"],
  ["1", "tight"],
  ["1.5", "snug"],
  ["2", "base"],
  ["2.5", "firm"],
  ["3", "soft"],
  ["4", "wide"],
  ["5", "roomy"],
  ["6", "broad"],
  ["8", "deep"],
  ["10", "page"],
  ["12", "grand"],
]);

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

export async function codemodSpacing({ dry = false } = {}) {
  const stats = new Map();
  let files = 0;
  let total = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const { out, changed, counts } = rewriteSpacing(src, MAP);
    if (!changed) continue;
    files += 1;
    total += changed;
    for (const [tok, n] of counts) stats.set(tok, (stats.get(tok) ?? 0) + n);
    if (!dry) await writeFile(file, out);
  }
  return { files, total, stats };
}

function rampName(tok) {
  const hit = tok.match(new RegExp("^((?:[a-zA-Z0-9-]+:)*-?" + UTIL + ")-(.+)$"));
  if (!hit) return null;
  const named = MAP.get(hit[2]);
  return named === undefined ? null : `${hit[1]}-${named}`;
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const dry = process.argv.includes("--dry");
  codemodSpacing({ dry })
    .then(({ files, total, stats }) => {
      console.log(`${dry ? "[dry] " : ""}spacing-codemod: ${total} Klassen in ${files} Dateien`);
      for (const [k, v] of [...stats.entries()].sort((a, b) => b[1] - a[1])) {
        console.log(`  ${String(v).padStart(4)}  ${k} -> ${rampName(k)}`);
      }
    })
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}
