#!/usr/bin/env node
/**
 * Radius codemod.
 *
 * Four of the six substitutions are pixel-exact, verified against the built
 * CSS rather than from Tailwind's docs:
 *
 *   rounded-md    .375rem =  6px  ->  rounded-tile   6px   exact
 *   rounded-lg    .5rem   =  8px  ->  rounded-card   8px   exact
 *   rounded-xl    .75rem  = 12px  ->  rounded-sheet 12px   exact
 *   rounded-full  9999px          ->  rounded-pill  999px   indistinguishable
 *
 * Two are real moves, both chosen deliberately:
 *
 *   rounded       .25rem =  4px  ->  rounded-tile   6px   +2px on 346 sites
 *   rounded-2xl   1rem   = 16px ->  rounded-sheet 12px   -4px on   8 sites
 *
 * Bare `rounded` is the largest single item in this dimension and the one
 * that was invisible by design — it looks like "just the default" rather than
 * "a missing token". It sits on chips, small buttons, <pre> blocks,
 * progress bars and inputs. tile is the smallest named token and the only
 * one that fits that company; the +2px is the smallest move that lands on
 * the scale at all.
 *
 * Directional classes are mapped explicitly rather than derived, because
 * `rounded-tl` and `rounded-t-2xl` are not the same shape of thing as a
 * plain size and a clever split would silently produce invalid classes.
 *
 * Run with --dry to see the plan without writing.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const SCAN_EXT = [".tsx", ".jsx", ".ts", ".js"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// A Map, and read with .get only. Bracket notation on a Map walks the
// prototype chain, so `constructor` / `__proto__` read truthy while real
// classes read undefined — that replaced exactly the wrong tokens in the
// border codemod's first version.
const MAP = new Map([
  // Pixel-exact.
  ["rounded-md", "rounded-tile"],
  ["rounded-lg", "rounded-card"],
  ["rounded-xl", "rounded-sheet"],
  ["rounded-full", "rounded-pill"],

  // Deliberate moves.
  ["rounded", "rounded-tile"], // 4px -> 6px
  ["rounded-2xl", "rounded-sheet"], // 16px -> 12px

  // Directional, mapped by hand.
  ["rounded-tl", "rounded-tl-tile"],
  ["rounded-t-md", "rounded-t-tile"],
  ["rounded-t-2xl", "rounded-t-sheet"],
]);

// Backtick templates must allow newlines (see the border codemod for why);
// quoted JS strings cannot span raw newlines so those stay strict.
const CLASS_STRINGS = /"([^"\n]*)"|`([\s\S]*?)`|'([^'\n]*)'/g;

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
      const mapped = mapClass(tok);
      if (mapped === null) return tok;
      changed += 1;
      return mapped;
    })
    .join("");
  return { out, changed };
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

export async function codemodRadius({ dry = false } = {}) {
  const stats = new Map();
  let files = 0;
  let total = 0;

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
  codemodRadius({ dry })
    .then(({ files, total, stats }) => {
      console.log(`${dry ? "[dry] " : ""}radius-codemod: ${total} Klassen in ${files} Dateien`);
      for (const [k, v] of [...stats.entries()].sort((a, b) => b[1] - a[1])) {
        console.log(`  ${String(v).padStart(4)}  ${k} -> ${mapClass(k)}`);
      }
    })
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}
