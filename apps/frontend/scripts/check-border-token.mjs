#!/usr/bin/env node
/**
 * Border-token guard (ratchet).
 *
 * The border dimension was the most deceptive one in the audit: it *looks*
 * converged because every panel has a hairline — the hairlines were just named
 * `border-white/10` and `border-surface-border` instead of `border-line`.
 *
 * After the codemod: 952 border classes sit on the `line` tokens, 271 carry
 * foreign semantics (sky/amber/red/violet/emerald/rose/indigo/orange/blue/
 * teal/neutral) that mean something and need a per-case decision, and 4 are
 * white hairlines that land nowhere near a token.
 *
 * So this is a ratchet, not a clean-room check. The current off-token set is
 * recorded in scripts/border-baseline.json and tolerated; anything new fails.
 *
 * Allow-list rather than deny-list, for the reason documented in
 * check-field-surface.mjs: a deny-list of `white|neutral|gray` waves the next
 * `border-slate-300` straight through.
 *
 * Run with --update to re-record the baseline after an intentional migration.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "border-baseline.json");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// Border colours that may be used.
const TOKEN = new Set([
  "line",
  "line-subtle",
  "line-strong",
  "line-focus",
  "transparent",
  "inherit",
  "current",
  "accent",
  "accent-hover",
  "success",
  "success-hover",
  "warning",
  "warning-hover",
  "danger",
  "danger-hover",
]);

// Grey/white hairlines: never acceptable in new code, they are what the
// codemod replaced.
const GREYSCALE = /^(white|black|neutral-\d+|gray-\d+|zinc-\d+|slate-\d+)$/;

// Foreign semantic colours: not design tokens for borders.
const FOREIGN =
  /^(red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d+$/;

// Tailwind geometry / non-colour border utilities that must not be treated as
// colour decisions.
const GEOMETRY = new Set([
  "0", "2", "4", "8", "none", "solid", "dashed", "dotted", "double", "hidden",
  "collapse", "separate", "t", "r", "b", "l", "s", "e", "x", "y", "m",
]);

// The trailing boundary must accept the quote that closes a className
// attribute, not just whitespace. `(?=\s|$)` alone never matches the LAST
// class in every class string.
//
// The hyphen inside the character class is load-bearing: without it
// `border-sky-500` and `border-line-strong` stop at the first hyphen, fail
// the trailing lookahead, and vanish from the count — a guard that reported
// "3 off-token" while 275 sat in the tree.
const BORDER_CLASS =
  /(^|\s|["'`])((?:[a-zA-Z0-9-]+:)*border-([a-z0-9][a-z0-9/-]*))(?=[\s"'`]|$)/g;

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

// Strips variant prefixes and the /opacity suffix down to the colour stem.
function colourStem(cls) {
  const noVariant = cls.slice(cls.lastIndexOf(":") + 1);
  const bare = noVariant.replace(/^border-/, "");
  return bare.split("/")[0];
}

export async function checkBorderToken() {
  const baseline = JSON.parse(await readFile(BASELINE, "utf8"));
  const tolerated = new Set(baseline.classes ?? []);
  const violations = [];
  let checked = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const m of src.matchAll(BORDER_CLASS)) {
      const cls = m[2];
      const stem = colourStem(cls);
      if (GEOMETRY.has(stem)) continue;
      checked += 1;
      if (TOKEN.has(stem)) continue;
      const key = `${rel}::${cls}`;
      if (tolerated.has(key)) continue;
      const kind = GREYSCALE.test(stem)
        ? "grey/white hairline"
        : FOREIGN.test(stem)
          ? "foreign semantic"
          : "unknown border colour";
      violations.push({ file: rel, cls, kind });
    }
  }
  return { violations, checked, tolerated: tolerated.size };
}

async function update() {
  const classes = {};
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const m of src.matchAll(BORDER_CLASS)) {
      const cls = m[2];
      const stem = colourStem(cls);
      if (GEOMETRY.has(stem) || TOKEN.has(stem)) continue;
      classes[`${rel}::${cls}`] = true;
    }
  }
  const keys = Object.keys(classes).sort();
  await writeFile(
    BASELINE,
    JSON.stringify({ classes: keys, note: "Tolerated off-token border classes. Re-record with --update after an intentional migration; new ones fail." }, null, 2) + "\n"
  );
  console.log(`[border-token] recorded ${keys.length} tolerated classes`);
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  if (process.argv.includes("--update")) {
    update().catch((e) => { console.error(e); process.exit(1); });
  } else {
    checkBorderToken()
      .then(({ violations, checked, tolerated }) => {
        if (violations.length) {
          console.error(`[border-token] FAILED - ${violations.length} new off-token border class(es):`);
          for (const v of violations.slice(0, 25)) {
            console.error(`  ${v.file}: ${v.cls}  (${v.kind})`);
          }
          if (violations.length > 25) console.error(`  … und ${violations.length - 25} weitere`);
          process.exit(1);
        }
        console.log(
          `[border-token] OK - ${checked} border colour classes checked, ${tolerated} baselined, no new drift`
        );
      })
      .catch((e) => { console.error(e); process.exit(1); });
  }
}
