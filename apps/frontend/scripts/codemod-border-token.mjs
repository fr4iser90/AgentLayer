#!/usr/bin/env node
/**
 * Border-token codemod.
 *
 * Two kinds of thing are being replaced, and they are not equally mechanical:
 *
 * 1. The compat alias. `border-surface-border` points at LINE_DEFAULT, the same
 *    constant as `border-line`, so that substitution cannot change a single
 *    pixel. 661 occurrences, zero judgement.
 *
 * 2. Translucent white hairlines. `border-white/10` is not a colour, it is a
 *    function of whatever it sits on: on canvas it composites to #232426, on
 *    card to #35383f. The line tokens are opaque, so folding them onto a token
 *    necessarily picks one surface's answer for all of them.
 *
 * The map is anchored on `card` (#1E222A), the dominant content surface, where
 * the residual error is <= 10 RGB distance:
 *
 *   /5  -> line-subtle   #23282f   card delta  9.8   canvas delta 29.0
 *   /10 -> line         #2e343e   card delta  7.8   canvas delta 30.5
 *   /15 -> line-strong  #3f4753   card delta  9.9   canvas delta 42.7
 *   /20 -> line-strong  #3f4753   card delta 14.1   canvas delta 31.0
 *
 * On canvas a mapped hairline is therefore slightly brighter than before. That
 * is a real, deliberate change, not an oversight: the alternative was keeping
 * 291 translucent borders outside the token system, which is the state that
 * made this dimension look finished while it was not.
 *
 * /8, /30 and /40 are left alone — four occurrences that land nowhere near a
 * token (worst delta 102) and would be a lie to fold in.
 *
 * Run with --dry to see the diff without writing.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const SCAN_EXT = [".tsx", ".jsx", ".ts", ".js"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// Exact class -> replacement. Applied only to whole classes inside a class string.
//
// A Map, not an object literal: `MAP[tok]` on a plain object walks the
// prototype chain, so a class token of `__proto__` or `constructor` reads as
// truthy and would be replaced with `[object Object]` or the Object constructor
// source. The dry run caught exactly that before anything was written.
const MAP = new Map([
  // Compat alias: same constant, cannot change appearance.
  ["border-surface-border", "border-line"],
  ["border-surface-border/60", "border-line/60"],
  ["border-surface-border/80", "border-line/80"],
  ["divide-surface-border", "divide-line"],

  // Translucent hairlines folded onto the opaque ladder, card-anchored.
  ["border-white/5", "border-line-subtle"],
  ["border-white/10", "border-line"],
  ["border-white/15", "border-line-strong"],
  ["border-white/20", "border-line-strong"],
  ["divide-white/5", "divide-line-subtle"],
  ["divide-white/10", "divide-line"],
]);

// Class strings live in three quoting styles. Backtick templates must allow
// newlines: `className={`border-t border-white/5 ${cond ? "x" : ""}`}` spans
// several lines, and a [^`\n] class would silently never match it. Non-greedy
// pairing from each backtick is correct for well-formed alternating literals;
// requiring a newline inside is what breaks pairing, so nothing requires it.
// Quote-delimited JS strings cannot span raw newlines, so those stay strict.
const CLASS_STRINGS = /"([^"\n]*)"|`([\s\S]*?)`|'([^'\n]*)'/g;

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

// A class ends at whitespace or at the quote/backtick that closes the attribute.
// Stopping only at whitespace silently skips the last class of every string.
// Splits a Tailwind class into its variant prefix and its base class.
// `hover:border-white/10` -> ["hover:", "border-white/10"]
// `[&:hover]:border-x`   -> ["[&:hover]:", "border-x"]  (only the last colon
// separates prefix from class, so arbitrary variants survive)
function splitVariant(tok) {
  const i = tok.lastIndexOf(":");
  if (i === -1) return ["", tok];
  return [tok.slice(0, i + 1), tok.slice(i + 1)];
}

function mapClass(tok) {
  const [prefix, base] = splitVariant(tok);
  const mapped = MAP.get(base);
  if (mapped === undefined) return null;
  return prefix + mapped;
}

function replaceInClassString(raw) {
  let changed = 0;
  const out = raw
    .split(/(\s+)/)
    .map((tok) => {
      if (/^\s+$/.test(tok) || tok === "") return tok;
      // MAP.get via mapClass, never MAP[tok]: on a Map the bracket form reads
      // the prototype chain, so real classes resolve to undefined while
      // `constructor`, `toString` and `__proto__` resolve to truthy functions.
      // The bracket form therefore replaces exactly the tokens that must never
      // be touched and none of the ones that should be.
      const mapped = mapClass(tok);
      if (mapped === null) return tok;
      changed += 1;
      return mapped;
    })
    .join("");
  return { out, changed };
}

export async function codemodBorders({ dry = false } = {}) {
  const stats = new Map();
  let files = 0;
  let total = 0;

  // Stats are counted from the original text in the same pass that writes, not
  // from a second read: a second pass over already-rewritten files would report
  // zero and look like the codemod did nothing.
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    let changedInFile = 0;
    const out = src.replace(CLASS_STRINGS, (match, dq, bt, sq) => {
      const raw = dq ?? bt ?? sq ?? "";
      if (!raw) return match;
      const { out: mapped, changed } = replaceInClassString(raw);
      if (!changed) return match;
      changedInFile += changed;
      const quote = dq !== undefined && dq !== null ? '"' : bt !== undefined && bt !== null ? "`" : "'";
      return quote + mapped + quote;
    });
    if (changedInFile) {
      files += 1;
      total += changedInFile;
      for (const raw of src.match(CLASS_STRINGS) ?? []) {
        const inner = raw.slice(1, -1);
        for (const tok of inner.split(/\s+/)) {
          if (mapClass(tok) !== null) stats.set(tok, (stats.get(tok) ?? 0) + 1);
        }
      }
      if (!dry) await writeFile(file, out);
    }
  }

  return { files, total, stats };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const dry = process.argv.includes("--dry");
  codemodBorders({ dry }).then(({ files, total, stats }) => {
    console.log(`${dry ? "[dry] " : ""}border-codemod: ${total} Klassen in ${files} Dateien`);
    for (const [k, v] of [...stats.entries()].sort((a, b) => b[1] - a[1])) {
      console.log(`  ${String(v).padStart(4)}  ${k} -> ${mapClass(k)}`);
    }
  }).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
