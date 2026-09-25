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
 * The allowed token names are read from tailwind.config.js at runtime, not kept
 * here. The copy this guard used to carry listed four `line-*` names and eight
 * semantic ones, so the moment `unread`, `subagent` and `recording` were added
 * to the palette the guard failed a correct migration (`border-recording/50` →
 * "unknown border colour") while staying silent about a hairline that had no
 * business existing. A guard with its own list of another file's names is
 * guaranteed to disagree with it, and the disagreement always looks like the
 * other file is wrong.
 *
 * Run with --update to re-record the baseline after an intentional migration.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import config from "../tailwind.config.js";
import { bareClassName, intentionalReason, unhitIntentionalKeys } from "./intentional-colours.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "border-baseline.json");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// Border colours that may be used: every colour in the config, flattened one
// level (`line` plus `line-subtle`, `ink` plus `ink-on-fill`), plus the three
// keywords Tailwind resolves itself.
const TOKEN = new Set(["transparent", "inherit", "current"]);
for (const [name, value] of Object.entries(config.theme.extend.colors)) {
  if (typeof value === "string") TOKEN.add(name);
  else for (const sub of Object.keys(value)) TOKEN.add(sub === "DEFAULT" ? name : `${name}-${sub}`);
}

// Deliberately raw, with the reason stated where the check reads it. The list is
// shared with the fill and ink guards (scripts/intentional-colours.mjs): a
// catalogue key is usually a border, a fill and a label of the same thing, and
// three copies of one decision drift into three different claims about it.
//
// It lives there rather than in border-baseline.json because a baseline entry
// says "we have not got to this yet" while these say "there is nothing to get
// to", and only the second kind of sentence can be checked for still being true
// — an entry whose class has left the tree fails the run (see `stale`). Scoped
// to this guard's own property, so a justified fill can never count as a hit
// for a border.
const IS_BORDER = (cls) => cls.startsWith("border-");

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
export function colourStem(cls) {
  const noVariant = cls.slice(cls.lastIndexOf(":") + 1);
  const bare = noVariant.replace(/^border-/, "");
  const stem = bare.split("/")[0];
  // A direction segment is not part of the colour. `border-y-0` sets a width
  // on both horizontal edges; reading its stem as `y-0` missed GEOMETRY (which
  // holds `0`), so the guard called a width utility an unknown border COLOUR
  // and failed a build over `md:border-y-0`. Same family as the missing hyphen
  // and the missing `/`: the matcher classifies a shape it never intended to
  // match. Only a single direction letter counts, so `line-strong` — which
  // starts with `l` but continues with `i` — is left alone.
  const directional = /^([trblsexy])-(.+)$/.exec(stem);
  return directional ? directional[2] : stem;
}

/**
 * Pure matcher over one source string.
 *
 * Exported because the matcher is the layer that fails silently: every defect
 * found in this family so far (missing hyphen, missing `/`, missing variant
 * chain, and now the direction segment) produced a GREEN run that saw less
 * than the tree held. A guard whose classifier is only reachable through file
 * I/O cannot be pinned by a test, so the classification lives here.
 */
export function scanBorders(src) {
  const findings = [];
  for (const m of src.matchAll(BORDER_CLASS)) {
    const cls = m[2];
    const stem = colourStem(cls);
    if (GEOMETRY.has(stem)) continue;
    if (TOKEN.has(stem)) continue;
    const kind = GREYSCALE.test(stem)
      ? "grey/white hairline"
      : FOREIGN.test(stem)
        ? "foreign semantic"
        : "unknown border colour";
    findings.push({ cls, stem, kind });
  }
  return findings;
}

export async function checkBorderToken() {
  const baseline = JSON.parse(await readFile(BASELINE, "utf8"));
  const tolerated = new Set(baseline.classes ?? []);
  const violations = [];
  const hit = new Set();
  let checked = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    const seen = new Set();
    for (const finding of scanBorders(src)) {
      if (!seen.has(finding.cls)) {
        seen.add(finding.cls);
        checked += 1;
      }
      // Two keys, deliberately: the baseline records a class as written, so a
      // `hover:border-white/10` is tolerated only as exactly that — widening it
      // to the bare class would forgive `border-white/10` in plain state, which
      // is the one spelling the codemod removed. The allow-list is keyed bare,
      // because the justification there is about the colour, not the state.
      if (intentionalReason(rel, finding.cls)) {
        hit.add(`${rel}::${bareClassName(finding.cls)}`);
        continue;
      }
      if (tolerated.has(`${rel}::${finding.cls}`)) continue;
      violations.push({ file: rel, ...finding });
    }
  }
  // A justification that no longer names anything in the tree is not a
  // justification, it is a comment somebody forgot to delete. Failing on it
  // keeps the allow-list from becoming the thing the baseline was.
  const stale = unhitIntentionalKeys(hit, IS_BORDER);
  return { violations, checked, tolerated: tolerated.size, intentional: hit.size, stale };
}

async function update() {
  const classes = {};
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const m of src.matchAll(BORDER_CLASS)) {
      const cls = m[2];
      if (GEOMETRY.has(colourStem(cls)) || TOKEN.has(colourStem(cls))) continue;
      const key = `${rel}::${cls}`;
      // A justified class must not also sit in the baseline: two records of the
      // same decision, one of them silent, is how the drift came back before.
      if (intentionalReason(rel, cls)) continue;
      classes[key] = true;
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
      .then(({ violations, checked, tolerated, intentional, stale }) => {
        if (stale.length) {
          console.error(`[border-token] FAILED - ${stale.length} begründete Ausnahme(n) treffen nichts mehr:`);
          for (const k of stale) console.error(`  ${k}`);
          console.error("[border-token] Die Klasse ist nicht mehr im Baum. Streiche die Begründung, sonst liest sie als Erlaubnis für etwas, das es nicht gibt.");
          process.exit(1);
        }
        if (violations.length) {
          console.error(`[border-token] FAILED - ${violations.length} new off-token border class(es):`);
          for (const v of violations.slice(0, 25)) {
            console.error(`  ${v.file}: ${v.cls}  (${v.kind})`);
          }
          if (violations.length > 25) console.error(`  … und ${violations.length - 25} weitere`);
          process.exit(1);
        }
        console.log(
          `[border-token] OK - ${checked} border colour classes checked, ${tolerated} baselined, ${intentional} begründet roh, no new drift`
        );
      })
      .catch((e) => { console.error(e); process.exit(1); });
  }
}
