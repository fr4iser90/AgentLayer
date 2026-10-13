#!/usr/bin/env node
/**
 * Z-index guard (clean-room, no baseline).
 *
 * Stacking was the last unguarded dimension. `check-ink-color` guards text,
 * `check-border-token` hairlines, `check-fill-token` fills — `z-*` had nothing,
 * and 45 call sites had spread over nine values where the number had stopped
 * meaning anything: `z-50` carried both dropdown menus and full-screen modal
 * scrims, so a page-level menu could float over the dialog that had just
 * blocked the page, and modal alone used `z-50`, `z-[80]` and `z-[100]`.
 *
 * The scale in tailwind.config.js is a top-level `theme.zIndex`, NOT inside
 * `extend`, so it replaces Tailwind's defaults: `z-50` and `z-[100]` no longer
 * generate any CSS. That removes the capability rather than asking about it.
 * Two doors stay open and this guard closes them:
 *   - arbitrary values (`z-[7]`) always render, theme config cannot remove them;
 *   - an inline `style={{ zIndex: 50 }}` never touches the theme at all.
 *
 * Allowed names are read from tailwind.config.js at runtime. A guard keeping
 * its own copy of the list goes quiet the moment the real one changes — and a
 * name that is NOT in the scale is reported too, because a typo (`z-tooptip`)
 * renders nothing and leaves a layer silently unstacked.
 *
 * There is deliberately no baseline file. The migration left zero raw levels, so
 * a baseline would only be a place to hide one. The escape hatch is the config:
 * a new level means a new named token in tailwind.config.js, which makes the
 * decision visible in the diff of the file that owns the design.
 *
 * Run with --explain to print the scale and the level distribution.
 */
import { readFile, readdir } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import config from "../tailwind.config.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// The rendered scale. `theme.extend.zIndex` would only add to Tailwind's
// defaults, which is how raw levels sneak back while every name still matches.
const SCALE = config.theme?.zIndex ?? {};
const TOKENS = new Set(Object.keys(SCALE));

// Group 1 = boundary, 2 = variant chain, 3 = modifier + `z-`, 4 = value.
//
// The boundary must not be `\b`: `relative z-[1] mt-snug` has `]` on one side
// and a space on the other, both non-word, so an anchored scan finds nothing
// there — the defect that made an earlier grep report no arbitrary values while
// the tree held four. The variant chain must be consumed, or `hover:z-50` and
// the 206 prefixed classes the ink guard first missed go unseen.
const Z_RE =
  /(^|[^A-Za-z0-9])((?:[a-zA-Z0-9-]+:)*((?:!|-)?z-))(auto|[0-9]+|\[[^\]]*\]|[a-z][a-z0-9-]*)(?![A-Za-z0-9-])/g;

// `zIndex` written straight into a style object bypasses the theme entirely.
const INLINE_RE = /(?<![A-Za-z0-9])zIndex\s*[:]/g;

/**
 * Pure scan of one source string — exported so the matcher's own coverage is
 * testable. Every blind spot here is a silent undercount: the guard would not
 * report "I stopped seeing stacking", it would report "stacking is clean".
 */
export function scanZIndexes(src) {
  const found = [];

  Z_RE.lastIndex = 0;
  let m;
  while ((m = Z_RE.exec(src)) !== null) {
    // Group 2 already contains the variant chain AND the `z-`; group 3 is only
    // the modifier, used to tell `-z-lift` from `z-lift`. Concatenating both
    // reports `z-z-50`, which no line contains — so the line lookup below would
    // silently degrade to line 0 while still counting the violation.
    const [, boundary, head, mod, value] = m;
    let kind = null;
    if (mod.startsWith("-")) kind = "negative";
    else if (value.startsWith("[")) kind = "arbitrary";
    else if (/^[0-9]+$/.test(value)) kind = "raw";
    else if (!TOKENS.has(value)) kind = "unknown";
    if (kind)
      found.push({
        cls: `${head}${value}`,
        kind,
        value,
        line: lineOf(src, m.index + boundary.length),
      });
  }

  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(src)) !== null) {
    found.push({ cls: "zIndex:", kind: "inline", value: "zIndex", line: lineOf(src, m.index) });
  }

  return found;
}

const lineOf = (src, pos) => src.slice(0, pos).split("\n").length;

export async function checkZIndex() {
  const findings = [];
  const kinds = new Map();
  let total = 0;

  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file);
    const text = await readFile(file, "utf8");
    const issues = scanZIndexes(text);
    if (!issues.length) continue;
    for (const i of issues) {
      total += 1;
      kinds.set(i.kind, (kinds.get(i.kind) ?? 0) + 1);
    }
    findings.push({ file: rel, issues });
  }

  // A missing scale is not "nothing is allowed", it is "the config stopped
  // being the source" — say that instead of reporting every token as unknown.
  const scaleMissing = Object.keys(SCALE).length === 0;
  return { ok: findings.length === 0 && !scaleMissing, findings, kinds, total, scaleMissing };
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

const WHY = {
  raw: "rohe Stufe — die Skala ersetzt Tailwinds Default, sie erzeugt kein CSS mehr",
  arbitrary: "beliebiger Wert — erzeugt CSS und steht außerhalb der Skala",
  unknown: "Name nicht in der Skala — erzeugt kein CSS, die Ebene bleibt ungestapelt",
  negative: "negative Stufe — die Skala kennt keine, erzeugt kein CSS",
  inline: "zIndex im style-Objekt — umgeht das Theme vollständig",
};

async function main() {
  const { ok, findings, kinds, total, scaleMissing } = await checkZIndex();

  if (process.argv.includes("--explain")) {
    console.log(`[z-index] Skala aus tailwind.config.js (theme.zIndex):`);
    for (const [name, value] of Object.entries(SCALE))
      console.log(`  ${value.padStart(5)}  z-${name}`);
    console.log(`[z-index] ${total} Verstoß/Verstöße im Baum:`);
    for (const [k, n] of [...kinds.entries()].sort((a, b) => b[1] - a[1]))
      console.log(`  ${String(n).padStart(4)}  ${k}`);
    return;
  }

  if (scaleMissing) {
    console.error(
      "[z-index] theme.zIndex fehlt in tailwind.config.js — ohne Skala ist jeder Name erlaubt, das Gate meldet nichts."
    );
    process.exit(1);
  }

  if (!ok) {
    console.error(
      `[z-index] ${total} Verstoß/Verstöße in ${findings.length} Datei(en) — Stapelhöhe ist eine benannte Ebene, keine Zahl.`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8))
        console.error(`    L${i.line} ${i.cls} — ${WHY[i.kind]}`);
      if (issues.length > 8) console.error(`    … +${issues.length - 8} mehr`);
    }
    console.error(
      "\n[z-index] Ebene wählen, nicht Zahl: z-lift · z-canvas · z-docked · z-menu · z-overlay · z-modal · z-tooltip"
    );
    console.error(
      "[z-index] Braucht die Stelle wirklich eine neue Ebene? Token in tailwind.config.js ergänzen — nicht hier ausnehmen."
    );
    process.exit(1);
  }
  console.log(
    `[z-index] OK - keine rohe Stapelhöhe. ${TOKENS.size} Ebenen aus tailwind.config.js.`
  );
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}